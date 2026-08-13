#!/usr/bin/env python3
"""Build and deploy the CRX services on Northflank via the Northflank REST API.

This is the CD half of the pipeline: CI (`.github/workflows/ci.yml`) proves the
commit is good, then `.github/workflows/deploy-northflank.yml` runs this script
to roll that exact commit out to Northflank.

For each target service the script:

1. Reads the current deployment to discover which resource actually builds the
   image. For a combined service that is the service itself; for a deployment
   service it is the build service feeding it.
2. Starts a build of the requested commit SHA on that build source.
3. Polls until the build concludes, failing the run if the build fails.
4. Deploys the resulting build, unless the service already has continuous
   deployment enabled (`buildSHA == "latest"`), in which case Northflank rolls
   the new build out on its own.

Only the standard library is used so CI does not need a Python environment
beyond the interpreter itself.

Usage:
    python tools/northflank_deploy.py check
    python tools/northflank_deploy.py deploy --sha "$GITHUB_SHA"

Configuration is read from CLI flags, then environment variables, then `.env`,
then the defaults baked into `northflank.template.json`:

    NORTHFLANK_API_TOKEN   (required) Northflank API token
    NORTHFLANK_PROJECT_ID  project to deploy into
    NORTHFLANK_SERVICES    comma-separated service IDs
    NORTHFLANK_TEAM_ID     optional, for team-scoped tokens
    NORTHFLANK_API_HOST    optional, defaults to https://api.northflank.com
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "northflank.template.json"
ENV_PATH = REPO_ROOT / ".env"

DEFAULT_API_HOST = "https://api.northflank.com"
DEFAULT_SERVICES = ("crx-api", "crx-web")
DEFAULT_BRANCH = "main"

# Build states from GET /v1/projects/{p}/services/{s}/build/{b}.
SUCCESS_STATUS = "SUCCESS"
FAILED_STATUSES = frozenset({"ABORTED", "FAILURE", "SUBMISSION_FAILURE", "CRASHED"})

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4


class NorthflankError(RuntimeError):
    """A Northflank API call failed, or a build did not succeed."""


def load_env_file(path: Path, environ: dict[str, str]) -> None:
    """Merge `KEY=value` lines from `path` into `environ` without overriding it.

    Real environment variables win so that CI secrets always beat a stale local
    `.env`, which is the file developers keep their token in.
    """
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not key or key in environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        environ[key] = value


def template_defaults(path: Path = TEMPLATE_PATH) -> dict[str, str]:
    """Pull project ID and branch out of the Northflank template, if present."""
    if not path.is_file():
        return {}
    try:
        template = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    args = template.get("arguments")
    if not isinstance(args, dict):
        return {}
    return {k: v for k, v in args.items() if isinstance(v, str)}


@dataclass
class Config:
    token: str
    project_id: str
    services: tuple[str, ...]
    branch: str
    sha: str | None = None
    team_id: str | None = None
    api_host: str = DEFAULT_API_HOST
    poll_interval: float = 10.0
    timeout: float = 2700.0
    deploy: bool = True
    dry_run: bool = False


@dataclass
class ServiceResult:
    service: str
    build_source: str
    build_id: str | None = None
    status: str | None = None
    deployed: bool = False
    notes: list[str] = field(default_factory=list)


class NorthflankClient:
    """Thin Northflank REST client built on `urllib`, with retries on 5xx."""

    def __init__(
        self,
        token: str,
        api_host: str = DEFAULT_API_HOST,
        team_id: str | None = None,
        opener: Callable[[urllib.request.Request], Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._token = token
        self._api_host = api_host.rstrip("/")
        self._team_id = team_id
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep

    @property
    def _projects_base(self) -> str:
        if self._team_id:
            return f"/v1/teams/{self._team_id}/projects"
        return "/v1/projects"

    def _service_path(self, project_id: str, service_id: str, suffix: str = "") -> str:
        return f"{self._projects_base}/{project_id}/services/{service_id}{suffix}"

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self._api_host}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"

        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with self._opener(request) as response:
                    payload = response.read().decode("utf-8")
                return json.loads(payload) if payload.strip() else {}
            except urllib.error.HTTPError as exc:
                detail = _read_error_body(exc)
                if exc.code in RETRYABLE_STATUSES and attempt < MAX_ATTEMPTS:
                    last_error = exc
                    self._sleep(2**attempt)
                    continue
                raise NorthflankError(
                    f"{method} {path} failed with HTTP {exc.code}: {detail}"
                ) from exc
            except urllib.error.URLError as exc:
                if attempt < MAX_ATTEMPTS:
                    last_error = exc
                    self._sleep(2**attempt)
                    continue
                raise NorthflankError(f"{method} {path} failed: {exc.reason}") from exc
            except json.JSONDecodeError as exc:
                raise NorthflankError(f"{method} {path} returned invalid JSON: {exc}") from exc

        raise NorthflankError(f"{method} {path} failed after {MAX_ATTEMPTS} attempts: {last_error}")

    def get_service(self, project_id: str, service_id: str) -> dict:
        return self.request("GET", self._service_path(project_id, service_id)).get("data", {})

    def get_deployment(self, project_id: str, service_id: str) -> dict:
        path = self._service_path(project_id, service_id, "/deployment")
        return self.request("GET", path).get("data", {})

    def start_build(
        self,
        project_id: str,
        service_id: str,
        sha: str | None = None,
        branch: str | None = None,
    ) -> dict:
        body: dict[str, str] = {}
        if sha:
            body["sha"] = sha
        if branch:
            body["branch"] = branch
        path = self._service_path(project_id, service_id, "/build")
        return self.request("POST", path, body).get("data", {})

    def get_build(self, project_id: str, service_id: str, build_id: str) -> dict:
        path = self._service_path(project_id, service_id, f"/build/{build_id}")
        return self.request("GET", path).get("data", {})

    def set_deployment(self, project_id: str, service_id: str, body: dict) -> dict:
        path = self._service_path(project_id, service_id, "/deployment")
        return self.request("POST", path, body).get("data", {})


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - the original HTTP error matters more
        return exc.reason or ""
    return raw[:500].strip() or (exc.reason or "")


def resolve_build_source(client: NorthflankClient, project_id: str, service_id: str) -> dict:
    """Describe how `service_id` gets its image.

    Combined services build and deploy themselves; deployment services point at
    a separate build service. `buildSHA == "latest"` means continuous deployment
    is on, so a successful build rolls out without an explicit deploy call.
    """
    deployment = client.get_deployment(project_id, service_id)
    internal = deployment.get("internal") or {}
    if not internal:
        raise NorthflankError(
            f"Service '{service_id}' does not deploy a Northflank-built image "
            "(no internal build source). Point it at a Git repo or build service first."
        )
    return {
        "build_source": internal.get("nfObjectId") or service_id,
        "branch": internal.get("branch"),
        "cd_enabled": internal.get("buildSHA") == "latest",
        "deployed_sha": internal.get("deployedSHA"),
        "build_id": internal.get("buildId"),
    }


def wait_for_build(
    client: NorthflankClient,
    project_id: str,
    build_source: str,
    build_id: str,
    poll_interval: float,
    timeout: float,
    log: Callable[[str], None],
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict:
    deadline = monotonic() + timeout
    last_status: str | None = None
    while True:
        build = client.get_build(project_id, build_source, build_id)
        status = build.get("status")
        if status != last_status:
            log(f"  build {build_id}: {status}")
            last_status = status
        if build.get("concluded") or status == SUCCESS_STATUS or status in FAILED_STATUSES:
            return build
        if monotonic() >= deadline:
            raise NorthflankError(
                f"Build {build_id} did not finish within {timeout:.0f}s (last status: {status})"
            )
        sleep(poll_interval)


def deploy_service(
    client: NorthflankClient,
    config: Config,
    service_id: str,
    log: Callable[[str], None],
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> ServiceResult:
    log(f"{service_id}: resolving build source")
    source = resolve_build_source(client, config.project_id, service_id)
    build_source = source["build_source"]
    branch = source["branch"] or config.branch
    result = ServiceResult(service=service_id, build_source=build_source)

    if build_source != service_id:
        result.notes.append(f"builds from '{build_source}'")

    if config.dry_run:
        result.notes.append("dry run: no build started")
        log(f"{service_id}: dry run, would build {config.sha or branch} on '{build_source}'")
        return result

    # A build service needs to be told which branch to build; a combined service
    # infers it from its own Git configuration and rejects an explicit branch.
    service = client.get_service(config.project_id, build_source)
    is_build_service = service.get("serviceType") == "build"
    build = client.start_build(
        config.project_id,
        build_source,
        sha=config.sha,
        branch=branch if is_build_service else None,
    )
    build_id = build.get("id")
    if not build_id:
        raise NorthflankError(f"Northflank did not return a build ID for '{build_source}'")
    result.build_id = build_id
    log(f"{service_id}: started build {build_id} for {config.sha or branch}")

    finished = wait_for_build(
        client,
        config.project_id,
        build_source,
        build_id,
        config.poll_interval,
        config.timeout,
        log,
        sleep=sleep,
        monotonic=monotonic,
    )
    result.status = finished.get("status")
    if result.status != SUCCESS_STATUS:
        message = finished.get("message") or "no message"
        raise NorthflankError(f"Build {build_id} for '{service_id}' ended as {result.status}: {message}")

    if not config.deploy:
        result.notes.append("deploy skipped (--no-deploy)")
        return result

    if source["cd_enabled"]:
        result.deployed = True
        result.notes.append("continuous deployment enabled; Northflank rolls out the new build")
        log(f"{service_id}: CD enabled, Northflank will deploy build {build_id}")
        return result

    client.set_deployment(
        config.project_id,
        service_id,
        {
            "internal": {"id": build_source, "branch": branch, "buildId": build_id},
            "docker": {"configType": "default"},
        },
    )
    result.deployed = True
    log(f"{service_id}: deployed build {build_id}")
    return result


def check_services(
    client: NorthflankClient, config: Config, log: Callable[[str], None]
) -> list[ServiceResult]:
    results = []
    for service_id in config.services:
        source = resolve_build_source(client, config.project_id, service_id)
        result = ServiceResult(
            service=service_id,
            build_source=source["build_source"],
            build_id=source["build_id"],
        )
        result.notes.append(f"branch={source['branch']}")
        result.notes.append("cd=on" if source["cd_enabled"] else "cd=off")
        if source["deployed_sha"]:
            result.notes.append(f"deployed={source['deployed_sha'][:12]}")
        log(f"{service_id}: {', '.join(result.notes)}")
        results.append(result)
    return results


def build_config(args: argparse.Namespace, environ: dict[str, str]) -> Config:
    defaults = template_defaults()

    token = args.token or environ.get("NORTHFLANK_API_TOKEN")
    if not token:
        raise NorthflankError(
            "No Northflank API token. Set NORTHFLANK_API_TOKEN in the environment, "
            "in .env for local runs, or as a GitHub Actions repository secret."
        )

    project_id = args.project or environ.get("NORTHFLANK_PROJECT_ID") or defaults.get("projectId")
    if not project_id:
        raise NorthflankError("No Northflank project. Pass --project or set NORTHFLANK_PROJECT_ID.")

    services = _split_services(args.service) or _split_services(
        [environ.get("NORTHFLANK_SERVICES", "")]
    )
    if not services:
        services = DEFAULT_SERVICES

    branch = args.branch or environ.get("NORTHFLANK_BRANCH") or defaults.get("branch") or DEFAULT_BRANCH

    return Config(
        token=token,
        project_id=project_id,
        services=tuple(services),
        branch=branch,
        sha=args.sha or None,
        team_id=args.team or environ.get("NORTHFLANK_TEAM_ID") or None,
        api_host=args.api_host or environ.get("NORTHFLANK_API_HOST") or DEFAULT_API_HOST,
        poll_interval=args.poll_interval,
        timeout=args.timeout,
        deploy=not args.no_deploy,
        dry_run=args.dry_run,
    )


def _split_services(values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    for value in values:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    return out


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "command",
        nargs="?",
        default="deploy",
        choices=("deploy", "check"),
        help="'deploy' builds and rolls out a commit; 'check' only reports service state",
    )
    parser.add_argument("--sha", default="", help="Commit SHA to build (defaults to the branch head)")
    parser.add_argument("--branch", default="", help="Branch to build")
    parser.add_argument("--project", default="", help="Northflank project ID")
    parser.add_argument(
        "--service",
        action="append",
        default=[],
        help="Service ID to deploy; repeatable or comma-separated",
    )
    parser.add_argument("--team", default="", help="Northflank team ID for team-scoped tokens")
    parser.add_argument("--token", default="", help="Northflank API token (prefer the environment)")
    parser.add_argument("--api-host", default="", help=f"API host (default {DEFAULT_API_HOST})")
    parser.add_argument("--poll-interval", type=float, default=10.0, help="Seconds between build polls")
    parser.add_argument("--timeout", type=float, default=2700.0, help="Seconds to wait for a build")
    parser.add_argument("--no-deploy", action="store_true", help="Build only, do not roll out")
    parser.add_argument("--dry-run", action="store_true", help="Resolve config and services, change nothing")
    parser.add_argument("--env-file", default=str(ENV_PATH), help="Env file to read defaults from")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    environ = dict(os.environ)
    load_env_file(Path(args.env_file), environ)

    def log(message: str) -> None:
        print(message, flush=True)

    try:
        config = build_config(args, environ)
        client = NorthflankClient(config.token, config.api_host, config.team_id)
        log(f"Northflank project '{config.project_id}' services: {', '.join(config.services)}")

        if args.command == "check":
            check_services(client, config, log)
            return 0

        results = [deploy_service(client, config, service, log) for service in config.services]
    except NorthflankError as exc:
        print(f"error: {exc}", file=sys.stderr, flush=True)
        return 1

    for result in results:
        state = "deployed" if result.deployed else "built"
        suffix = f" ({'; '.join(result.notes)})" if result.notes else ""
        log(f"{result.service}: {state} {result.build_id or ''}{suffix}".rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

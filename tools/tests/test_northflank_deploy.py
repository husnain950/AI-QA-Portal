import json

import pytest
from fake_northflank import TOKEN, FakeNorthflank, FakeService

import northflank_deploy
from northflank_deploy import NorthflankError, load_env_file, main, template_defaults

SHA = "b" * 40


def run_script(server: FakeNorthflank, *args: str, token: str = TOKEN, env_file: str = "/nonexistent") -> int:
    """Invoke the CLI against the fake API, isolated from the real environment."""
    return main(
        [
            *args,
            "--api-host",
            server.url,
            "--token",
            token,
            "--project",
            "qa-pdf-portal",
            "--poll-interval",
            "0",
            "--env-file",
            env_file,
        ]
    )


def combined_services(**overrides: FakeService) -> dict[str, FakeService]:
    services = {"crx-api": FakeService(), "crx-web": FakeService()}
    services.update(overrides)
    return services


class TestConfigLoading:
    def test_env_file_fills_gaps_but_never_overrides_real_env(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "# a comment",
                    "",
                    "NORTHFLANK_API_TOKEN=from-file",
                    'NORTHFLANK_PROJECT_ID="quoted-project"',
                    "export NORTHFLANK_SERVICES=a,b",
                    "MALFORMED_LINE",
                ]
            ),
            encoding="utf-8",
        )
        environ = {"NORTHFLANK_API_TOKEN": "from-real-env"}
        load_env_file(env_file, environ)

        assert environ["NORTHFLANK_API_TOKEN"] == "from-real-env"
        assert environ["NORTHFLANK_PROJECT_ID"] == "quoted-project"
        assert environ["NORTHFLANK_SERVICES"] == "a,b"
        assert "MALFORMED_LINE" not in environ

    def test_missing_env_file_is_not_an_error(self, tmp_path):
        environ: dict[str, str] = {}
        load_env_file(tmp_path / "absent", environ)
        assert environ == {}

    def test_template_supplies_project_and_branch_defaults(self):
        defaults = template_defaults()
        assert defaults["projectId"] == "qa-pdf-portal"
        assert defaults["branch"] == "main"

    def test_missing_token_fails_with_actionable_message(self, capsys, monkeypatch, tmp_path):
        monkeypatch.delenv("NORTHFLANK_API_TOKEN", raising=False)
        exit_code = main(["deploy", "--env-file", str(tmp_path / "absent")])
        assert exit_code == 1
        assert "NORTHFLANK_API_TOKEN" in capsys.readouterr().err

    def test_services_can_be_given_comma_separated_or_repeated(self):
        args = northflank_deploy.parse_args(
            ["deploy", "--service", "one,two", "--service", "three"]
        )
        config = northflank_deploy.build_config(args, {"NORTHFLANK_API_TOKEN": "t"})
        assert config.services == ("one", "two", "three")


class TestDeploy:
    def test_builds_the_requested_sha_and_deploys_it(self, capsys):
        with FakeNorthflank(combined_services()) as server:
            exit_code = run_script(server, "deploy", "--sha", SHA)

        assert exit_code == 0
        out = capsys.readouterr().out

        builds = server.calls("POST", "/build")
        assert [c.path.split("/services/")[1] for c in builds] == ["crx-api/build", "crx-web/build"]
        assert all(c.body == {"sha": SHA} for c in builds)

        deploys = server.calls("POST", "/deployment")
        assert len(deploys) == 2
        assert deploys[0].body == {
            "internal": {"id": "crx-api", "branch": "main", "buildId": "crx-api-build-1"},
            "docker": {"configType": "default"},
        }
        assert "crx-api: deployed crx-api-build-1" in out
        assert "crx-web: deployed crx-web-build-2" in out

    def test_skips_explicit_deploy_when_continuous_deployment_is_on(self, capsys):
        services = combined_services(**{"crx-api": FakeService(internal={"buildSHA": "latest"})})
        with FakeNorthflank(services) as server:
            exit_code = run_script(server, "deploy", "--sha", SHA)

        assert exit_code == 0
        deployed_services = {c.path.split("/services/")[1] for c in server.calls("POST", "/deployment")}
        assert deployed_services == {"crx-web/deployment"}
        assert "CD enabled" in capsys.readouterr().out

    def test_a_failed_build_fails_the_run_and_stops_before_deploying(self, capsys):
        services = combined_services(
            **{
                "crx-api": FakeService(
                    build_statuses=["BUILDING", "FAILURE"], build_message="npm ci exited 1"
                )
            }
        )
        with FakeNorthflank(services) as server:
            exit_code = run_script(server, "deploy", "--sha", SHA)

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "ended as FAILURE" in captured.err
        assert "npm ci exited 1" in captured.err
        assert server.calls("POST", "/deployment") == []
        # crx-web is never touched once crx-api fails.
        assert server.calls("POST", "crx-web") == []

    def test_deployment_service_builds_on_its_build_service(self):
        services = {
            "crx-web": FakeService(
                service_type="deployment", internal={"nfObjectId": "crx-web-builder"}
            ),
            "crx-web-builder": FakeService(service_type="build"),
        }
        with FakeNorthflank(services) as server:
            exit_code = run_script(server, "deploy", "--sha", SHA, "--service", "crx-web")

        assert exit_code == 0
        build = server.calls("POST", "/build")[0]
        assert build.path.endswith("/services/crx-web-builder/build")
        # Build services require an explicit branch; combined services reject one.
        assert build.body == {"sha": SHA, "branch": "main"}
        deploy = server.calls("POST", "/deployment")[0]
        assert deploy.path.endswith("/services/crx-web/deployment")
        assert deploy.body["internal"]["id"] == "crx-web-builder"

    def test_no_deploy_builds_without_rolling_out(self):
        with FakeNorthflank(combined_services()) as server:
            exit_code = run_script(server, "deploy", "--sha", SHA, "--no-deploy")

        assert exit_code == 0
        assert len(server.calls("POST", "/build")) == 2
        assert server.calls("POST", "/deployment") == []

    def test_dry_run_touches_nothing(self, capsys):
        with FakeNorthflank(combined_services()) as server:
            exit_code = run_script(server, "deploy", "--sha", SHA, "--dry-run")

        assert exit_code == 0
        assert server.calls("POST", "/build") == []
        assert server.calls("POST", "/deployment") == []
        assert "dry run" in capsys.readouterr().out

    def test_service_without_a_northflank_build_source_is_rejected(self, capsys):
        services = {"crx-api": FakeService(internal=None)}
        with FakeNorthflank(services) as server:
            exit_code = run_script(server, "deploy", "--sha", SHA, "--service", "crx-api")

        assert exit_code == 1
        assert "does not deploy a Northflank-built image" in capsys.readouterr().err

    def test_bad_token_surfaces_the_api_error(self, capsys):
        with FakeNorthflank(combined_services()) as server:
            exit_code = run_script(server, "deploy", "--sha", SHA, token="wrong-token")

        assert exit_code == 1
        assert "HTTP 401" in capsys.readouterr().err
        assert server.unauthorized


class TestCheck:
    def test_check_reports_state_without_building(self, capsys):
        services = combined_services(**{"crx-web": FakeService(internal={"buildSHA": "latest"})})
        with FakeNorthflank(services) as server:
            exit_code = run_script(server, "check")

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "crx-api: branch=main, cd=off" in out
        assert "crx-web: branch=main, cd=on" in out
        assert server.calls("POST", "/build") == []


class TestTransport:
    def test_transient_5xx_responses_are_retried(self):
        with FakeNorthflank({"crx-api": FakeService()}, fail_times=2) as server:
            client = northflank_deploy.NorthflankClient(
                TOKEN, server.url, sleep=lambda _seconds: None
            )
            data = client.get_service("qa-pdf-portal", "crx-api")

        assert data["id"] == "crx-api"
        assert len(server.requests) == 3

    def test_persistent_5xx_responses_give_up_with_the_body(self):
        with FakeNorthflank({"crx-api": FakeService()}, fail_times=99) as server:
            client = northflank_deploy.NorthflankClient(
                TOKEN, server.url, sleep=lambda _seconds: None
            )
            with pytest.raises(NorthflankError) as excinfo:
                client.get_service("qa-pdf-portal", "crx-api")

        assert "HTTP 503" in str(excinfo.value)
        assert "temporarily unavailable" in str(excinfo.value)

    def test_team_scoped_token_uses_the_team_path(self):
        with FakeNorthflank({"crx-api": FakeService()}) as server:
            client = northflank_deploy.NorthflankClient(TOKEN, server.url, team_id="my-team")
            client.get_service("qa-pdf-portal", "crx-api")

        assert server.requests[0].path == "/v1/teams/my-team/projects/qa-pdf-portal/services/crx-api"

    def test_build_timeout_is_reported(self):
        clock = iter([0.0, 0.0, 100.0, 200.0])
        with FakeNorthflank({"crx-api": FakeService(build_statuses=["BUILDING"])}) as server:
            client = northflank_deploy.NorthflankClient(TOKEN, server.url)
            with pytest.raises(NorthflankError) as excinfo:
                northflank_deploy.wait_for_build(
                    client,
                    "qa-pdf-portal",
                    "crx-api",
                    "build-1",
                    poll_interval=0,
                    timeout=60,
                    log=lambda _message: None,
                    sleep=lambda _seconds: None,
                    monotonic=lambda: next(clock),
                )

        assert "did not finish within 60s" in str(excinfo.value)


class TestWorkflowWiring:
    """The workflows are the only thing that actually runs this script in CI."""

    @staticmethod
    def workflow(name: str) -> str:
        path = northflank_deploy.REPO_ROOT / ".github" / "workflows" / name
        return path.read_text(encoding="utf-8")

    def test_deploy_workflow_runs_on_pushes_to_main_with_the_secret(self):
        content = self.workflow("deploy-northflank.yml")
        assert "tools/northflank_deploy.py" in content
        assert "secrets.NORTHFLANK_API_TOKEN" in content
        assert "github.sha" in content

    def test_ci_workflow_covers_the_documented_test_commands(self):
        content = self.workflow("ci.yml")
        assert "pytest apps/api/backend/tests" in content
        assert "tools/run_tests_smoke.py" in content
        assert "npm run build" in content

    def test_template_and_workflow_agree_on_the_deploy_branch(self):
        template = json.loads((northflank_deploy.TEMPLATE_PATH).read_text(encoding="utf-8"))
        assert template["arguments"]["branch"] == "main"

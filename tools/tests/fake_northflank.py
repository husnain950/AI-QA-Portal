"""A minimal in-process stand-in for the Northflank REST API.

Serves the handful of endpoints `tools/northflank_deploy.py` uses so the deploy
script can be exercised over real HTTP, and records every request it receives so
tests can assert on the exact payloads that would hit Northflank.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

SERVICE_RE = re.compile(r"^/v1/(?:teams/(?P<team>[^/]+)/)?projects/(?P<project>[^/]+)/services/(?P<rest>.+)$")

TOKEN = "nf-test-token"


@dataclass
class FakeService:
    """One Northflank service, plus the build states its polls should report."""

    service_type: str = "combined"
    # A mapping overrides the default internal build source; `None` makes the
    # service deploy an external registry image instead.
    internal: dict[str, Any] | None = field(default_factory=dict)
    build_statuses: list[str] = field(default_factory=lambda: ["BUILDING", "SUCCESS"])
    build_message: str = "Image successfully built"

    def deployment_payload(self, service_id: str) -> dict[str, Any]:
        if self.internal is None:
            return {"external": {"imagePath": "nginx:latest"}}
        internal = {
            "nfObjectId": service_id,
            "nfObjectType": "service",
            "branch": "main",
            "buildId": "previous-build-1",
            "buildSHA": "aa" * 20,
        }
        internal.update(self.internal)
        return {"internal": internal}


@dataclass
class Recorded:
    method: str
    path: str
    body: dict[str, Any] | None


class FakeNorthflank:
    """Runs the fake API on a background thread; use as a context manager."""

    def __init__(self, services: dict[str, FakeService], fail_times: int = 0) -> None:
        self.services = services
        self.fail_times = fail_times
        self.requests: list[Recorded] = []
        self.unauthorized: list[str] = []
        self._build_polls: dict[str, int] = {}
        self._build_counter = 0
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> FakeNorthflank:
        handler = _make_handler(self)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()
        assert self._thread is not None
        self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    # -- assertions helpers ------------------------------------------------
    def calls(self, method: str, path_contains: str) -> list[Recorded]:
        return [r for r in self.requests if r.method == method and path_contains in r.path]

    def next_build_id(self, service_id: str) -> str:
        with self._lock:
            self._build_counter += 1
            return f"{service_id}-build-{self._build_counter}"

    def poll_status(self, service_id: str, build_id: str) -> tuple[str, bool]:
        service = self.services[service_id]
        with self._lock:
            index = self._build_polls.get(build_id, 0)
            self._build_polls[build_id] = index + 1
        statuses = service.build_statuses
        status = statuses[min(index, len(statuses) - 1)]
        concluded = status == "SUCCESS" or status in {"FAILURE", "ABORTED", "CRASHED"}
        return status, concluded

    def take_failure(self) -> bool:
        with self._lock:
            if self.fail_times > 0:
                self.fail_times -= 1
                return True
        return False


def _make_handler(state: FakeNorthflank) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:  # keep pytest output clean
            pass

        def _read_body(self) -> dict[str, Any] | None:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return None
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _send(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _handle(self, method: str) -> None:
            body = self._read_body()
            state.requests.append(Recorded(method, self.path, body))

            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                state.unauthorized.append(self.path)
                self._send(401, {"error": {"message": "Unauthorized"}})
                return

            if state.take_failure():
                self._send(503, {"error": {"message": "temporarily unavailable"}})
                return

            match = SERVICE_RE.match(self.path)
            if not match:
                self._send(404, {"error": {"message": "no such route"}})
                return

            rest = match.group("rest").split("/")
            service_id = rest[0]
            service = state.services.get(service_id)
            if service is None:
                self._send(404, {"error": {"message": f"service {service_id} not found"}})
                return
            tail = rest[1:]

            if method == "GET" and not tail:
                self._send(200, {"data": {"id": service_id, "serviceType": service.service_type}})
            elif method == "GET" and tail == ["deployment"]:
                self._send(200, {"data": service.deployment_payload(service_id)})
            elif method == "POST" and tail == ["deployment"]:
                self._send(200, {"data": {}})
            elif method == "POST" and tail == ["build"]:
                build_id = state.next_build_id(service_id)
                self._send(200, {"data": {"id": build_id, "status": "QUEUED", "concluded": False}})
            elif method == "GET" and len(tail) == 2 and tail[0] == "build":
                status, concluded = state.poll_status(service_id, tail[1])
                self._send(
                    200,
                    {
                        "data": {
                            "id": tail[1],
                            "status": status,
                            "concluded": concluded,
                            "success": status == "SUCCESS",
                            "message": service.build_message,
                        }
                    },
                )
            else:
                self._send(404, {"error": {"message": f"unhandled {method} {self.path}"}})

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._handle("POST")

    return Handler

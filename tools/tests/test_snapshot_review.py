"""Cover the three things `snapshot_review` has to get right.

The retry test is not hypothetical: the first real run against the deployed portal died
with `http.client.IncompleteRead` because the starved container truncated a response
mid-stream. Without a retry, a snapshot silently loses documents that read fine a second
later.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import snapshot_review
from snapshot_review import snapshot


class FakePortal:
    """Serves /api/documents and the per-document export, with scripted failures."""

    def __init__(self, documents: list[dict], fail_times: dict[str, int] | None = None) -> None:
        self.documents = documents
        self.fail_times = dict(fail_times or {})
        self.hits: list[str] = []
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> FakePortal:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        assert self._server is not None and self._thread is not None
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def take_failure(self, doc_id: str) -> bool:
        with self._lock:
            remaining = self.fail_times.get(doc_id, 0)
            if remaining > 0:
                self.fail_times[doc_id] = remaining - 1
                return True
        return False


def _make_handler(state: FakePortal) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:  # keep pytest output clean
            pass

        def _send(self, code: int, payload: object) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = self.path
            state.hits.append(path)

            if path == "/api/documents":
                self._send(200, state.documents)
                return

            if path.startswith("/api/documents/") and "/export" in path:
                doc_id = path[len("/api/documents/") :].split("/")[0]
                if state.take_failure(doc_id):
                    self._send(503, {"detail": "starved"})
                    return
                self._send(200, {"document": {"name": doc_id}, "sections": []})
                return

            self._send(404, {"detail": "no such route"})

    return Handler


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries are real; their sleeps are not worth the wall clock."""
    monkeypatch.setattr(snapshot_review.time, "sleep", lambda _seconds: None)


def read_snapshot(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_a_truncated_response_is_retried_not_lost(tmp_path):
    documents = [{"id": "a", "name": "Act A"}, {"id": "b", "name": "Act B"}]
    with FakePortal(documents, fail_times={"b": 2}) as portal:
        written = read_snapshot(snapshot(portal.url, tmp_path))

    assert written["document_count"] == 2
    assert written["failed"] == []
    assert [d["name"] for d in written["documents"]] == ["Act A", "Act B"]


def test_a_document_that_never_responds_is_reported_and_the_rest_survive(tmp_path):
    documents = [{"id": "a", "name": "Act A"}, {"id": "b", "name": "Act B"}]
    # More failures than MAX_ATTEMPTS, so 'b' can never be fetched.
    with FakePortal(documents, fail_times={"b": 99}) as portal:
        written = read_snapshot(snapshot(portal.url, tmp_path))

    assert written["document_count"] == 1
    assert [d["name"] for d in written["documents"]] == ["Act A"]
    assert [f["name"] for f in written["failed"]] == ["Act B"]


def test_an_empty_corpus_refuses_to_overwrite_a_good_snapshot(tmp_path):
    """The bug that started all this rendered a failed load as an empty corpus.

    A snapshot must never turn that into an empty file sitting next to real ones.
    """
    with FakePortal([]) as portal:
        with pytest.raises(SystemExit, match="empty corpus"):
            snapshot(portal.url, tmp_path)

    assert list(tmp_path.iterdir()) == []

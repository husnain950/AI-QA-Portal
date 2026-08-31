"""The multipart encoder used to re-seed a deployed portal over its HTTP API."""

from email import message_from_bytes

from backend import push_corpus
from backend.services import blob_store


def _parts(body: bytes, content_type: str):
    """Decode with the stdlib email parser (``cgi`` is gone in 3.13)."""
    message = message_from_bytes(
        b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    assert message.is_multipart(), "encoder did not produce a parseable multipart body"
    found = {}
    for part in message.get_payload():
        disposition = part.get("Content-Disposition", "")
        name = part.get_param("name", header="Content-Disposition")
        found[name] = {
            "value": part.get_payload(decode=True),
            "filename": part.get_filename(),
            "type": part.get_content_type(),
            "disposition": disposition,
        }
    return found


def test_multipart_round_trips_fields_and_binary_files(tmp_path):
    pdf = tmp_path / "act.pdf"
    # Bytes that would corrupt if the encoder ever treated the body as text, including
    # a line that looks like a boundary delimiter.
    raw = b"%PDF-1.4\r\n\x00\xff\xfe binary \r\n--not-a-boundary--\r\n"
    pdf.write_bytes(raw)
    js = tmp_path / "act.json"
    js.write_text('{"metadata": {"total_pages": 1}}', encoding="utf-8")

    body, content_type = push_corpus.multipart(
        {"name": "Customs Act, 1969 — 30.06.2025"},
        {"pdf": ("act.pdf", str(pdf)), "json_file": ("act.json", str(js))},
    )
    assert content_type.startswith("multipart/form-data; boundary=")

    parts = _parts(body, content_type)
    assert set(parts) == {"name", "pdf", "json_file"}
    assert parts["name"]["value"].decode("utf-8") == "Customs Act, 1969 — 30.06.2025"
    assert parts["pdf"]["filename"] == "act.pdf"
    assert parts["pdf"]["value"] == raw, "binary must survive verbatim"
    assert parts["pdf"]["type"] == "application/pdf"
    assert parts["json_file"]["value"] == js.read_bytes()
    assert parts["json_file"]["type"] == "application/json"


def test_multipart_uses_a_fresh_boundary_each_call(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    files = {"pdf": ("a.pdf", str(pdf))}
    _, first = push_corpus.multipart({"name": "a"}, files)
    _, second = push_corpus.multipart({"name": "a"}, files)
    assert first != second


def test_risky_documents_are_ordered_first():
    """The largest documents must go while a crash is still free.

    On a deployment without a persistent volume, a document that OOMs the container
    destroys everything already uploaded. Sending the risky ones last -- which is what
    ascending size does -- put failure exactly where it cost the most: 89 of 91
    documents were lost that way, twice. They now go first, against an empty database.
    """
    mb = 1048576
    pending = [
        (1 * mb, "tiny", "t.pdf", "t.json"),
        (60 * mb, "huge", "h.pdf", "h.json"),
        (2 * mb, "small", "s.pdf", "s.json"),
        (20 * mb, "big", "b.pdf", "b.json"),
    ]
    risky, rest = push_corpus.plan_order(pending, 15 * mb)

    assert [item[1] for item in risky] == ["huge", "big"], "largest first"
    assert [item[1] for item in rest] == ["tiny", "small"], "then smallest-first"
    assert len(risky) + len(rest) == len(pending), "nothing may be dropped"


def test_plan_order_handles_an_all_small_corpus():
    mb = 1048576
    pending = [(1 * mb, "a", "", ""), (2 * mb, "b", "", "")]
    risky, rest = push_corpus.plan_order(pending, 15 * mb)
    assert risky == []
    assert [item[1] for item in rest] == ["a", "b"]


def test_plan_refresh_splits_by_content_hash(tmp_path):
    """A deployment serving a stale parse must be detected from the list alone."""
    same = tmp_path / "same.json"
    same.write_text('{"metadata": {"ocr": {"pages": 3}}}', encoding="utf-8")
    drifted = tmp_path / "drifted.json"
    drifted.write_text('{"metadata": {"ocr": {"pages": 9}}}', encoding="utf-8")
    fresh = tmp_path / "fresh.json"
    fresh.write_text("{}", encoding="utf-8")

    local = [
        push_corpus.LocalDoc(10, "Identical Act", "a.pdf", str(same), "customs",
                             "Identical Act", "acts"),
        push_corpus.LocalDoc(20, "Stale Act", "b.pdf", str(drifted), "finance",
                             "Stale Act", "acts"),
        push_corpus.LocalDoc(30, "New Act", "c.pdf", str(fresh), "sales_tax",
                             "New Act", "acts"),
    ]
    remote = {
        "key:Identical Act": {
            "id": "id-1",
            "json_filename": f"json/{blob_store.sha256_file(same)}.json",
        },
        # Production still holds the parse from before the OCR metadata existed.
        "key:Stale Act": {"id": "id-2", "json_filename": "json/" + "0" * 64 + ".json"},
    }

    to_upload, to_refresh = push_corpus.plan_refresh(local, remote)
    assert [item.name for item in to_upload] == ["New Act"], "absent -> upload"
    assert to_refresh == [(  # id first, so the caller can address replace-json
        "id-2", 20, "Stale Act", "b.pdf", str(drifted), "finance",
        "Stale Act", "acts",
    )]
    assert not any(item[2] == "Identical Act" for item in to_refresh), (
        "matching content hash must not cost a new version"
    )


def test_plan_refresh_matches_on_source_key_not_name(tmp_path):
    """Identity is the corpus key. The name is a display string.

    Two editions can carry the same ``name`` -- the old matching collapsed them onto
    one remote row and each push overwrote the other, silently.
    """
    body = tmp_path / "a.json"
    body.write_text("{}", encoding="utf-8")
    digest = f"json/{blob_store.sha256_file(body)}.json"

    local = [
        push_corpus.LocalDoc(10, "Customs Act", "a.pdf", str(body), "customs",
                             "Customs Act 2024", "acts"),
        push_corpus.LocalDoc(10, "Customs Act", "b.pdf", str(body), "customs",
                             "Customs Act 2025", "acts"),
    ]
    remote = {"key:Customs Act 2024": {"id": "id-1", "json_filename": digest}}

    to_upload, to_refresh = push_corpus.plan_refresh(local, remote)
    assert [item.source_key for item in to_upload] == ["Customs Act 2025"]
    assert to_refresh == [], "identical content must not cost a version"


def test_a_document_with_no_corpus_key_still_matches_by_name(tmp_path):
    """The bridge for documents uploaded by hand, which have no corpus identity."""
    body = tmp_path / "a.json"
    body.write_text("{}", encoding="utf-8")

    local = [push_corpus.LocalDoc(10, "Hand Upload", "a.pdf", str(body), "manual",
                                  None, None)]
    remote = {"name:Hand Upload": {"id": "id-1", "json_filename": "json/" + "0" * 64 + ".json"}}

    to_upload, to_refresh = push_corpus.plan_refresh(local, remote)
    assert to_upload == []
    assert to_refresh[0][0] == "id-1"


def test_remote_key_prefers_the_corpus_key():
    assert push_corpus.remote_key(
        {"name": "Some Act", "source_key": "Some Act, 2024"}
    ) == "key:Some Act, 2024"
    assert push_corpus.remote_key({"name": "Some Act", "source_key": None}) == "name:Some Act"


def test_libpq_url_strips_sqlalchemy_driver():
    assert push_corpus.libpq_url("postgresql+psycopg://crx:crx@127.0.0.1:5432/crx") == (
        "postgresql://crx:crx@127.0.0.1:5432/crx"
    )
    assert push_corpus.libpq_url("postgresql://crx:crx@127.0.0.1:5432/crx") == (
        "postgresql://crx:crx@127.0.0.1:5432/crx"
    )


def test_login_rejects_non_admin(monkeypatch):
    """replace-json is admin-gated; a reviewer session must not proceed."""

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"email":"r@example.com","role":"reviewer"}'

    class FakeOpener:
        handlers = []

        def open(self, request, timeout=0):
            return FakeResponse()

    try:
        push_corpus.login("https://portal.example", "r@example.com", "x" * 12, FakeOpener())
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "admin" in str(exc)


def test_main_requires_credentials_for_live_push(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(push_corpus, "local_documents", lambda: [])
    try:
        push_corpus.main(["--base-url", "https://portal.example"])
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "ADMIN_EMAIL" in str(exc)

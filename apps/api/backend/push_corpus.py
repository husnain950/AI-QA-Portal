"""Push a local corpus into a *deployed* portal over its own HTTP API.

A deployment has no source PDFs of its own -- they are not in git, and the pipeline
repositories are not on the server -- so ``sync_acts`` cannot run there. This walks the
local database and re-uploads each document to a remote instance instead.

**Riskiest first.** On a deployment without a persistent volume a container loses
everything it holds when it restarts, so a document that crashes it destroys the whole
run -- ordering by ascending size put exactly those documents last, where failure was
most expensive. (Northflank's ``crx-api`` does have a volume now; the ordering still
matters for any host that does not, and costs nothing where it is redundant.) The
largest are therefore attempted first, while the database is still empty and a crash
costs nothing; whatever survives that phase is kept, whatever kills the server is
reported and skipped, and the remainder then goes up smallest-first.

Documents already present by name are compared by content hash: identical ones are
skipped, drifted ones are re-sent as a new JSON version. It is safe to re-run and safe
to resume after an interruption.

    python -m backend.push_corpus --base-url https://your-portal.example.com
    python -m backend.push_corpus --base-url ... --dry-run

Credentials: ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD`` (or ``--email`` / ``--password``).
Every API path needs a session after the auth migration; replace-json and the v2 upload
commit path need an admin role.

Documents keep the identity they have locally. A corpus document is sent with its
``source_key`` and ``corpus_origin``, so the deployment mints the same ``uuid5``
``sync_acts`` does and a pushed row is indistinguishable from a synced one: pipeline
health metrics match on ``source_key`` and light up, a re-push is a new *version*
carrying review state rather than a second row, and reconciliation can see the
document. Only a document that has no corpus identity locally is still sent as an
``upload``.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, NamedTuple

import psycopg

from backend.database import DATABASE_URL, normalize_database_url
from backend.services.auth import SESSION_COOKIE
from backend.services.blob_store import sha256_file, upload_root

UPLOADS = upload_root()


class LocalDoc(NamedTuple):
    """One document to send, ordered by size (``plan_order`` sorts these directly)."""

    size: int
    name: str
    pdf: str
    json: str
    lane: str | None
    source_key: str | None
    corpus_origin: str | None
BASE = ""
_OPENER: urllib.request.OpenerDirector | None = None


def multipart(fields, files):
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += value.encode() + b"\r\n"
    for name, (filename, path) in files.items():
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
        ).encode()
        body += f"Content-Type: {ctype}\r\n\r\n".encode()
        with open(path, "rb") as handle:
            body += handle.read()
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def plan_order(pending, threshold_bytes):
    """Order the upload queue: riskiest first, then the rest smallest-first.

    ``pending`` is a list of ``(size, name, pdf, json)``. Returns ``(risky, rest)``.
    Kept separate from ``main`` so the ordering -- the part that decides how much a
    crash costs -- is testable without a network.
    """
    risky = sorted((item for item in pending if item[0] >= threshold_bytes), reverse=True)
    rest = sorted(item for item in pending if item[0] < threshold_bytes)
    return risky, rest


def libpq_url(url: str | None = None) -> str:
    """SQLAlchemy DSN → libpq DSN for sync ``psycopg.connect``."""
    raw = normalize_database_url(url or os.environ.get("DATABASE_URL", DATABASE_URL))
    if raw.startswith("postgresql+psycopg://"):
        return "postgresql://" + raw[len("postgresql+psycopg://") :]
    return raw


def local_documents(uploads: str | None = None) -> list[LocalDoc]:
    """Every locally stored document, with the identity it will keep on the remote.

    Withdrawn documents are skipped: the local pipeline stopped producing them, so
    pushing them would re-seed a deployment with parses that have been retired.
    """
    root = uploads if uploads is not None else UPLOADS
    todo: list[LocalDoc] = []
    with psycopg.connect(libpq_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name, pdf_filename, json_filename, corpus_lane, "
                "       source_key, corpus_origin "
                "FROM documents WHERE withdrawn_at IS NULL"
            )
            rows = cursor.fetchall()
    for name, pdf_filename, json_filename, lane, source_key, origin in rows:
        pdf = os.path.join(root, pdf_filename)
        js = os.path.join(root, json_filename)
        if os.path.exists(pdf) and os.path.exists(js):
            size = os.path.getsize(pdf) + os.path.getsize(js)
            todo.append(LocalDoc(size, name, pdf, js, lane, source_key, origin))
    todo.sort()
    return todo


def build_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def login(base_url: str, email: str, password: str, opener: urllib.request.OpenerDirector) -> dict[str, Any]:
    """POST /api/auth/login and keep the session cookie on ``opener``."""
    payload = json.dumps({"email": email, "password": password}).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/auth/login",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with opener.open(request, timeout=60) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read()[:300]
        raise SystemExit(
            f"error: login failed ({error.code}): {detail!r}. "
            f"Set ADMIN_EMAIL / ADMIN_PASSWORD (or --email / --password) to an "
            f"admin account on the deployment."
        ) from error
    if body.get("role") != "admin":
        raise SystemExit(
            f"error: signed in as {body.get('email')!r} with role "
            f"{body.get('role')!r}; push-remote needs an admin session "
            f"(replace-json and corpus uploads are admin-gated)."
        )
    jar = next(
        (
            handler.cookiejar
            for handler in opener.handlers
            if isinstance(handler, urllib.request.HTTPCookieProcessor)
        ),
        None,
    )
    cookie_names = {cookie.name for cookie in jar} if jar is not None else set()
    if SESSION_COOKIE not in cookie_names:
        raise SystemExit(
            f"error: login succeeded but no {SESSION_COOKIE!r} cookie was set. "
            f"Check that the portal is not stripping Secure cookies on a plain-http URL."
        )
    return body


def open_url(request: urllib.request.Request, timeout: float = 120):
    if _OPENER is None:
        return urllib.request.urlopen(request, timeout=timeout)
    return _OPENER.open(request, timeout=timeout)


def remote_key(doc) -> str:
    """How a remote document is recognised.

    Its ``source_key`` when it has one, and only then its name. Matching on the name
    alone was the old behaviour and it is a display string: two editions sharing one
    would silently become a single document.
    """
    return f"key:{doc['source_key']}" if doc.get("source_key") else f"name:{doc['name']}"


def existing_docs():
    """``{key: {"id", "json_filename"}}`` for everything already on the deployment."""
    request = urllib.request.Request(
        f"{BASE}/api/documents", headers={"Accept": "application/json"}
    )
    with open_url(request, timeout=120) as response:
        return {
            remote_key(doc): {"id": doc["id"], "json_filename": doc["json_filename"]}
            for doc in json.loads(response.read().decode())
        }


def plan_refresh(local, remote):
    """Split local documents into ``(to_upload, to_refresh)``.

    ``documents.json_filename`` is the blob's own sha256 (``json/<sha256>.json``), so a
    deployment serving a stale parse is detectable from the list endpoint alone -- no
    JSON has to be downloaded to notice the drift. Absent -> upload; present and equal
    -> skipped entirely; present and different -> a new version of the JSON only, since
    the PDF is content-addressed too and has not moved.

    ``local`` is a list of :class:`LocalDoc`. Network-free, so the part that decides
    what gets overwritten is testable.
    """
    to_upload, to_refresh = [], []
    for item in local:
        match = remote.get(
            f"key:{item.source_key}" if item.source_key else f"name:{item.name}"
        )
        if match is None:
            to_upload.append(item)
        elif match["json_filename"] != f"json/{sha256_file(item.json)}.json":
            to_refresh.append((match["id"], *item))
    return to_upload, to_refresh


def main(argv: list[str] | None = None):
    global BASE, _OPENER
    parser = argparse.ArgumentParser(description="Push a local corpus to a deployment")
    parser.add_argument("--base-url", required=True, help="deployed portal root URL")
    parser.add_argument(
        "--dry-run", action="store_true", help="list what would be sent, send nothing"
    )
    parser.add_argument(
        "--risky-above-mb",
        type=float,
        default=15.0,
        help="documents at least this large go first, while a crash is still free",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("ADMIN_EMAIL", ""),
        help="admin email (default: ADMIN_EMAIL)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("ADMIN_PASSWORD", ""),
        help="admin password (default: ADMIN_PASSWORD)",
    )
    args = parser.parse_args(argv)
    BASE = args.base_url.rstrip("/")

    need_remote = not args.dry_run or bool(args.email and args.password)
    if need_remote:
        if not args.email or not args.password:
            raise SystemExit(
                "error: ADMIN_EMAIL and ADMIN_PASSWORD (or --email / --password) "
                "are required to sign in to the deployment"
            )
        _OPENER = build_opener()
        user = login(BASE, args.email, args.password, _OPENER)
        print(f"signed in as {user.get('email')} ({user.get('role')})", flush=True)

    todo = local_documents()
    present = existing_docs() if need_remote else {}
    to_upload, to_refresh = plan_refresh(todo, present)

    upload_bytes = sum(item.size for item in to_upload)
    refresh_bytes = sum(os.path.getsize(item[4]) for item in to_refresh)
    local_keys = {
        f"key:{item.source_key}" if item.source_key else f"name:{item.name}"
        for item in todo
    }
    orphans = set(present) - local_keys
    print(
        f"{len(todo)} local documents, {len(present)} on production: "
        f"{len(to_refresh)} to refresh ({refresh_bytes / 1048576:.0f} MB of JSON), "
        f"{len(to_upload)} to upload ({upload_bytes / 1048576:.0f} MB), "
        f"{len(todo) - len(to_upload) - len(to_refresh)} already identical",
        flush=True,
    )
    if orphans:
        print(
            f"{len(orphans)} document(s) on production have no local match -- left "
            f"alone, "
            f"this tool never deletes",
            flush=True,
        )

    if args.dry_run:
        for _id, size, name, _pdf, js, lane, _key, _origin in to_refresh:
            print(
                f"  would refresh {os.path.getsize(js) / 1048576:6.1f} MB  "
                f"[{lane or '-'}]  {name}"
            )
        for item in to_upload:
            seeded = "corpus" if item.source_key else "upload"
            print(f"  would send    {item.size / 1048576:6.1f} MB  "
                  f"[{item.lane or '-'}/{seeded}]  {item.name}")
        return 0

    done = failed = 0
    sent = 0
    started = time.time()
    total = len(to_refresh) + len(to_upload)

    def send(label, url, fields, files, name, size):
        """POST one document. Returns True on success; reports and skips on failure."""
        nonlocal done, failed, sent
        body, ctype = multipart(fields, files)
        request = urllib.request.Request(url, data=body, method="POST")
        request.add_header("Content-Type", ctype)
        for attempt in (1, 2):
            try:
                with open_url(request, timeout=900) as response:
                    json.loads(response.read().decode() or "null")
                done += 1
                sent += size
                print(
                    f"  [{done:3d}/{total}] {label} {size / 1048576:6.1f} MB  "
                    f"{sent / 1048576:6.0f} MB sent  "
                    f"{(time.time() - started) / 60:4.1f} min  {name[:48]}",
                    flush=True,
                )
                return True
            except Exception as error:
                if attempt == 2:
                    failed += 1
                    detail = getattr(error, "read", lambda: b"")()[:200]
                    print(
                        f"  FAILED {label} {name[:48]}: {error} {detail!r}",
                        file=sys.stderr,
                        flush=True,
                    )
                    return False
                time.sleep(5)

    # Refresh first: it is JSON only, and it is what makes an already-visible library
    # tell the truth about its OCR provenance. Uploads can take their time afterwards.
    for doc_id, _size, name, _pdf, js, lane, _key, _origin in to_refresh:
        fields = {"note": "Corpus refresh from push_corpus."}
        if lane:
            fields["corpus_lane"] = lane
        send(
            "refresh",
            f"{BASE}/api/documents/{doc_id}/replace-json",
            fields,
            {"json_file": (os.path.basename(js), js)},
            name,
            os.path.getsize(js),
        )

    risky, rest = plan_order(to_upload, args.risky_above_mb * 1048576)
    if risky:
        print(
            f"phase 1: {len(risky)} document(s) at or above "
            f"{args.risky_above_mb:.0f} MB, sent first while a crash costs nothing",
            flush=True,
        )
    for size, name, pdf, js, lane, source_key, origin in risky + rest:
        fields = {"name": name}
        if lane:
            fields["corpus_lane"] = lane
        # The identity this document already has locally. Without it the deployment
        # mints a uuid4 and a `source_type='upload'` row, which is what made pipeline
        # health unmatchable and a re-push destructive.
        if source_key:
            fields["source_key"] = source_key
        if origin:
            fields["corpus_origin"] = origin
        send(
            "upload ",
            f"{BASE}/api/documents/upload",
            fields,
            {
                "pdf": (os.path.basename(pdf), pdf),
                "json_file": (os.path.basename(js), js),
            },
            name,
            size,
        )

    print(
        f"\ndone: {done} sent, {failed} failed, "
        f"{(time.time() - started) / 60:.1f} min",
        flush=True,
    )
    if failed:
        print(
            f"NOTE: {failed} document(s) were not sent -- listed above. They are stale "
            f"or absent on the deployment, not silently merged.",
            flush=True,
        )
    print(f"{BASE} now has {len(existing_docs())} documents", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

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

Note this creates ``source_type='upload'`` documents: deterministic corpus ids and
pipeline health metrics come from ``sync_acts``, which needs the pipeline repositories.
Where the server can see them, prefer that.
"""

import argparse
import json
import mimetypes
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid

from backend.database import DB_PATH as DB
from backend.services.blob_store import sha256_file, upload_root

UPLOADS = upload_root()
BASE = ""


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


def existing_docs():
    """``{name: {"id", "json_filename"}}`` for everything already on the deployment."""
    request = urllib.request.Request(f"{BASE}/api/documents")
    with urllib.request.urlopen(request, timeout=120) as response:
        return {
            doc["name"]: {"id": doc["id"], "json_filename": doc["json_filename"]}
            for doc in json.load(response)
        }


def plan_refresh(local, remote):
    """Split local documents into ``(to_upload, to_refresh)``.

    ``documents.json_filename`` is the blob's own sha256 (``json/<sha256>.json``), so a
    deployment serving a stale parse is detectable from the list endpoint alone -- no
    JSON has to be downloaded to notice the drift. Absent -> upload; present and equal
    -> skipped entirely; present and different -> a new version of the JSON only, since
    the PDF is content-addressed too and has not moved.

    ``local`` is a list of ``(size, name, pdf, js, lane)``. Network-free, so the part
    that decides what gets overwritten is testable.
    """
    to_upload, to_refresh = [], []
    for item in local:
        name, js = item[1], item[3]
        match = remote.get(name)
        if match is None:
            to_upload.append(item)
        elif match["json_filename"] != f"json/{sha256_file(js)}.json":
            to_refresh.append((match["id"], *item))
    return to_upload, to_refresh


def main():
    global BASE
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
    args = parser.parse_args()
    BASE = args.base_url.rstrip("/")

    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    todo = []
    for row in connection.execute(
        "SELECT name, pdf_filename, json_filename, corpus_lane FROM documents"
    ):
        pdf = os.path.join(UPLOADS, row["pdf_filename"])
        js = os.path.join(UPLOADS, row["json_filename"])
        if os.path.exists(pdf) and os.path.exists(js):
            size = os.path.getsize(pdf) + os.path.getsize(js)
            todo.append((size, row["name"], pdf, js, row["corpus_lane"]))
    todo.sort()

    present = existing_docs()
    to_upload, to_refresh = plan_refresh(todo, present)
    upload_bytes = sum(item[0] for item in to_upload)
    refresh_bytes = sum(os.path.getsize(item[4]) for item in to_refresh)
    orphans = set(present) - {item[1] for item in todo}
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
        for _id, size, name, _pdf, js, lane in to_refresh:
            print(
                f"  would refresh {os.path.getsize(js) / 1048576:6.1f} MB  "
                f"[{lane or '-'}]  {name}"
            )
        for size, name, _pdf, _js, lane in to_upload:
            print(f"  would send    {size / 1048576:6.1f} MB  [{lane or '-'}]  {name}")
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
                with urllib.request.urlopen(request, timeout=900) as response:
                    json.load(response)
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
    for doc_id, _size, name, _pdf, js, lane in to_refresh:
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
    for size, name, pdf, js, lane in risky + rest:
        fields = {"name": name}
        if lane:
            fields["corpus_lane"] = lane
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

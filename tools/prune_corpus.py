#!/usr/bin/env python3
"""Delete every portal document that is not on a shortlist CSV.

The shortlist names PDFs; the portal does not store PDF names. `documents.pdf_filename`
is content-addressed (`pdf/<sha256>.pdf`) and `documents.name` is the JSON stem, which
the ordinance lane rewrites on ingest -- `Income Tax Ordinance, 2001 Amended upto
20.02.2026.pdf` is stored as `Income Tax Ordinance 2001 - amended upto 20.02.2026`.
Matching on the name alone therefore deletes documents the shortlist asked to keep.

So the primary key here is the PDF's sha256: hash the shortlist's PDFs where they sit
on disk and compare against `pdf_filename`. That is immune to every rename. The
normalised-name comparison is the fallback, for shortlist rows whose PDF is not staged
locally -- it folds case, whitespace, commas, dashes and a missing `.pdf`, all of which
occur in real rows.

Deletion reuses `DELETE /api/documents/{id}`, which already cascades and unlinks
unreferenced blobs, followed by `DELETE /api/corpus/orphans` for the tables that name a
document by bare text. Going over HTTP rather than SQL is what lets the same run work
against the deployed portal, whose Postgres is not reachable from outside.

Dry run is the default. Nothing is deleted without `--apply`.

Only the standard library is used, matching `northflank_deploy.py` and
`snapshot_review.py`. Sign-in uses ADMIN_EMAIL / ADMIN_PASSWORD (or --email/--password);
every delete needs an admin session.

Usage:
    python tools/prune_corpus.py --csv shortlist.csv                    # dry run, local
    python tools/prune_corpus.py --csv shortlist.csv --apply
    python tools/prune_corpus.py --csv shortlist.csv --base-url https://portal --apply
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.cookiejar
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_CORPUS_ROOT = REPO_ROOT / "data" / "corpora"
# A mis-parsed CSV should fail loudly rather than empty the portal. Raise it knowingly.
DEFAULT_MAX_DELETE = 80
TIMEOUT = 120
MAX_ATTEMPTS = 4
# A HEAVY 429 frees up only when the hour-long window rolls; capping the wait lower
# just burns attempts on a sleep that was never going to be long enough.
MAX_RETRY_WAIT = 3900
# Must stay <= MAX_BULK_DELETE in backend.routes.documents. The real ceiling is not
# the API but the proxy in front of it: 67 documents in one transaction 504'd against
# the deployed portal, where nginx gives up long before Postgres does. Keep a chunk
# small enough to commit inside that timeout, and few enough to fit the 10/hour budget.
BULK_CHUNK = 10
SESSION_COOKIE = "crx_session"  # must match backend.services.auth.SESSION_COOKIE

_SHA_IN_KEY = re.compile(r"([0-9a-f]{64})")


def norm(name: str) -> str:
    """Fold a PDF name to something two spellings of the same document share."""
    text = unicodedata.normalize("NFKC", name).strip()
    text = re.sub(r"\.pdf$", "", text, flags=re.I).strip()
    # The ordinance lane swaps ", " for " - "; the spreadsheet is inconsistent about both.
    text = re.sub(r"[,\-‒–—]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def read_shortlist(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"error: {path} has no rows")
    column = next((c for c in rows[0] if c and c.strip().lower() == "file name"), None)
    if column is None:
        raise SystemExit(
            f"error: {path} has no 'File name' column (found: {', '.join(rows[0])})"
        )
    for row in rows:
        row["_name"] = row.get(column) or ""
    return [row for row in rows if row["_name"].strip()]


def hash_corpus(corpus_root: Path) -> dict[str, str]:
    """normalised pdf stem -> sha256, for every PDF staged on disk."""
    digests: dict[str, str] = {}
    if not corpus_root.is_dir():
        return digests
    for pdf in sorted(corpus_root.glob("**/*.pdf")):
        digest = hashlib.sha256()
        with pdf.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        digests.setdefault(norm(pdf.name), digest.hexdigest())
    return digests


def build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


def login(base_url: str, email: str, password: str, opener) -> None:
    payload = json.dumps({"email": email, "password": password}).encode()
    request = urllib.request.Request(
        f"{base_url}/api/auth/login",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            response.read()
    except urllib.error.HTTPError as error:
        raise SystemExit(
            f"error: login failed ({error.code}): {error.read()[:300]!r}. "
            "Set ADMIN_EMAIL / ADMIN_PASSWORD (or --email / --password)."
        ) from error
    jar = next(
        h.cookiejar for h in opener.handlers
        if isinstance(h, urllib.request.HTTPCookieProcessor)
    )
    if SESSION_COOKIE not in {c.name for c in jar}:
        raise SystemExit(f"error: login sent no {SESSION_COOKIE!r} cookie")


def call(opener, url: str, method: str = "GET", payload: Any = None) -> Any:
    """One API call, retrying only what a retry can fix.

    Every DELETE lands in the API's HEAVY bucket (10/hour per IP), which is why the
    prune deletes in bulk rather than per document. A 429 is still possible when
    something else has spent the budget, so honour Retry-After rather than failing a
    half-finished prune.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with opener.open(request, timeout=TIMEOUT) as response:
                body = response.read()
            return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == MAX_ATTEMPTS:
                detail = error.read()[:300]
                raise SystemExit(
                    f"error: {method} {url} failed ({error.code}): {detail!r}"
                ) from error
            delay = min(int(error.headers.get("Retry-After") or 60), MAX_RETRY_WAIT)
            print(f"  rate limited; waiting {delay}s (attempt {attempt}/{MAX_ATTEMPTS})")
            time.sleep(delay)
    raise SystemExit(f"error: {method} {url} still rate limited after {MAX_ATTEMPTS} attempts")


def resolve(documents: list[dict], shortlist: list[dict], digests: dict[str, str]):
    """Split the portal's documents into keep and delete against the shortlist."""
    wanted_shas, wanted_names = set(), set()
    per_row: dict[str, dict] = {}
    for row in shortlist:
        key = norm(row["_name"])
        per_row[key] = row
        wanted_names.add(key)
        if key in digests:
            wanted_shas.add(digests[key])

    keep, delete, matched = [], [], set()
    for doc in documents:
        found = _SHA_IN_KEY.search(doc.get("pdf_filename") or "")
        sha = found.group(1) if found else None
        name_key = norm(doc.get("name") or "")
        if sha and sha in wanted_shas:
            keep.append(doc)
            matched.update(k for k in wanted_names if digests.get(k) == sha)
        elif name_key in wanted_names:
            keep.append(doc)
            matched.add(name_key)
        else:
            delete.append(doc)
    unmatched = [per_row[k] for k in wanted_names - matched]
    return keep, delete, unmatched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", required=True, type=Path, help="shortlist CSV")
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--email", default=os.environ.get("ADMIN_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD"))
    parser.add_argument("--max-delete", type=int, default=DEFAULT_MAX_DELETE)
    parser.add_argument(
        "--chunk", type=int, default=BULK_CHUNK,
        help=f"documents per delete request (default {BULK_CHUNK}); lower it if the "
             "portal sits behind a proxy that times out first",
    )
    parser.add_argument("--apply", action="store_true", help="actually delete")
    args = parser.parse_args(argv)

    if not args.email or not args.password:
        raise SystemExit("error: set ADMIN_EMAIL / ADMIN_PASSWORD or pass --email/--password")
    base_url = args.base_url.rstrip("/")

    shortlist = read_shortlist(args.csv)
    digests = hash_corpus(args.corpus_root)
    opener = build_opener()
    login(base_url, args.email, args.password, opener)
    documents = call(opener, f"{base_url}/api/documents")

    keep, delete, unmatched = resolve(documents, shortlist, digests)

    print(f"portal      : {base_url}")
    print(f"shortlist   : {len(shortlist)} rows ({args.csv.name})")
    print(f"pdfs hashed : {len(digests)} under {args.corpus_root}")
    print(f"documents   : {len(documents)}")
    print(f"  keep      : {len(keep)}")
    print(f"  delete    : {len(delete)}")
    print(f"  shortlist rows with no document: {len(unmatched)}")
    print()
    for doc in sorted(delete, key=lambda d: (d.get("corpus_lane") or "", d.get("name") or "")):
        print(f"  DELETE  [{doc.get('corpus_lane') or '-':<20}] {doc.get('name')}")
    if unmatched:
        print()
        for row in sorted(unmatched, key=lambda r: r["_name"]):
            print(f"  ABSENT  {row['_name'].strip()}")

    if not args.apply:
        print("\ndry run -- nothing deleted. Re-run with --apply.")
        return 0
    if not delete:
        print("\nnothing to delete.")
        return 0
    if len(delete) > args.max_delete:
        raise SystemExit(
            f"\nerror: {len(delete)} deletions exceeds --max-delete={args.max_delete}. "
            "Check the CSV parsed correctly before raising the ceiling."
        )

    print()
    # One request per chunk, not one per document: a per-document loop 429s after ten.
    for start in range(0, len(delete), args.chunk):
        chunk = delete[start:start + args.chunk]
        result = call(
            opener,
            f"{base_url}/api/documents",
            method="DELETE",
            payload={"ids": [doc["id"] for doc in chunk]},
        )
        print(f"  deleted {result['deleted']} documents "
              f"({start + len(chunk)}/{len(delete)})")

    swept = call(opener, f"{base_url}/api/corpus/orphans", method="DELETE")
    print(f"\norphans swept: {json.dumps(swept.get('deleted', {}), sort_keys=True)}")
    print(f"retained     : {json.dumps(swept.get('retained', {}), sort_keys=True)}")
    print(f"\ndeleted {len(delete)} documents; {len(keep)} remain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

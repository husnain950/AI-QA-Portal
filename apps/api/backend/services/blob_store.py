"""Content-addressed storage for the PDF and JSON blobs under ``UPLOAD_DIR``.

A source PDF never changes, so it is stored once under its own sha256 and shared by
every row that points at it; only the JSON is versioned.  Names are stored *relative*
to ``UPLOAD_DIR`` (``pdf/<sha256>.pdf``, ``json/<sha256>.json``) because that is what
``documents.pdf_filename`` holds and what the ``/uploads`` static mount serves, so the
frontend keeps building the same ``${STATIC}/uploads/${filename}`` URL it always did.

``UPLOAD_DIR`` is read at call time, never bound at import: ``runtime_sandbox``
monkeypatches ``runtime.UPLOAD_DIR`` and a module-level copy would silently write to
the real uploads directory during tests.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from typing import Optional

import aiosqlite

from backend import runtime

SUFFIXES = {"pdf": ".pdf", "json": ".json"}
_BLOB_NAME_RE = re.compile(r"^(pdf|json)/[0-9a-f]{64}\.(pdf|json)$")
_CHUNK = 1024 * 1024


def upload_root() -> str:
    return runtime.UPLOAD_DIR


def blob_path(rel_name: str) -> str:
    """Absolute path for a stored name. Also accepts legacy flat names."""
    return os.path.join(upload_root(), rel_name)


def is_blob_name(name: str) -> bool:
    """True for names this module produced (as opposed to a legacy flat upload)."""
    return bool(_BLOB_NAME_RE.match(name or ""))


def rel_name(kind: str, digest: str) -> str:
    return f"{kind}/{digest}{SUFFIXES[kind]}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def usable(path: str | os.PathLike) -> bool:
    """True when the path exists and is non-empty.

    Zero-byte leftovers from an interrupted write must not count as present, or the
    database ends up pointing at an unreadable upload.
    """
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def _commit(destination: str, write) -> bool:
    """Write through a temp file + ``os.replace``. False when already stored."""
    if usable(destination):
        return False
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    staged = f"{destination}.{os.getpid()}.staging"
    try:
        write(staged)
        os.replace(staged, destination)
    except BaseException:
        if os.path.exists(staged):
            os.remove(staged)
        raise
    return True


def store_bytes(data: bytes, kind: str) -> str:
    """Store ``data`` and return its name relative to ``UPLOAD_DIR``."""
    if kind not in SUFFIXES:
        raise ValueError(f"unknown blob kind: {kind}")
    name = rel_name(kind, sha256_bytes(data))
    _commit(blob_path(name), lambda staged: _write_bytes(staged, data))
    return name


def store_file(source: str | os.PathLike, kind: str) -> str:
    """Copy a file into the store and return its name relative to ``UPLOAD_DIR``."""
    if kind not in SUFFIXES:
        raise ValueError(f"unknown blob kind: {kind}")
    name = rel_name(kind, sha256_file(source))
    _commit(blob_path(name), lambda staged: shutil.copy2(source, staged))
    return name


async def store_upload(upload, kind: str) -> str:
    """Stream an uploaded file to the store without holding it in memory.

    ``store_bytes(await upload.read(), ...)`` buffers the whole file, which is fine
    locally and fatal on a small container: a 57 MB PDF took the 256 MB deployment down
    mid-import. The hash is computed as the bytes go past, so the content address costs
    no second pass.

    ``upload`` is anything with an async ``read(size)`` -- Starlette's ``UploadFile``.
    """
    if kind not in SUFFIXES:
        raise ValueError(f"unknown blob kind: {kind}")
    directory = os.path.join(upload_root(), kind)
    os.makedirs(directory, exist_ok=True)
    staged = os.path.join(directory, f".incoming.{os.getpid()}.{id(upload):x}")
    digest = hashlib.sha256()
    try:
        with open(staged, "wb") as target:
            while True:
                chunk = await upload.read(_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        name = rel_name(kind, digest.hexdigest())
        destination = blob_path(name)
        if usable(destination):
            os.remove(staged)      # already stored; the upload was a duplicate
        else:
            os.replace(staged, destination)
        return name
    except BaseException:
        if os.path.exists(staged):
            os.remove(staged)
        raise


def _write_bytes(path: str, data: bytes) -> None:
    with open(path, "wb") as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())


async def is_referenced(
    db: aiosqlite.Connection,
    name: str,
    *,
    ignore_document_id: Optional[str] = None,
) -> bool:
    """True when any row still points at this stored name.

    Checked before unlinking, because content addressing means two documents that were
    given the same PDF share one file on disk — deleting one must not blind the other.
    ``document_versions`` is consulted too: an old version keeps its JSON blob alive.
    """
    document_sql = """
        SELECT 1 FROM documents
        WHERE (pdf_filename = ? OR json_filename = ?)
    """
    params: list = [name, name]
    if ignore_document_id is not None:
        document_sql += " AND id != ?"
        params.append(ignore_document_id)
    async with db.execute(document_sql + " LIMIT 1", params) as cursor:
        if await cursor.fetchone() is not None:
            return True

    async with db.execute(
        "SELECT 1 FROM document_versions WHERE json_filename = ? LIMIT 1",
        (name,),
    ) as cursor:
        return await cursor.fetchone() is not None


async def unlink_if_unreferenced(
    db: aiosqlite.Connection,
    name: Optional[str],
    *,
    ignore_document_id: Optional[str] = None,
) -> bool:
    """Remove a stored blob when nothing references it. Never raises."""
    if not name:
        return False
    if await is_referenced(db, name, ignore_document_id=ignore_document_id):
        return False
    path = blob_path(name)
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
    except OSError:
        pass
    return False


def demo() -> None:
    """Self-check: dedupe, relative naming, and the zero-byte repair."""
    import tempfile

    with tempfile.TemporaryDirectory() as root:
        original, runtime.UPLOAD_DIR = runtime.UPLOAD_DIR, root
        try:
            first = store_bytes(b"%PDF-1.4 hello", "pdf")
            second = store_bytes(b"%PDF-1.4 hello", "pdf")
            assert first == second, "identical bytes must share one name"
            assert is_blob_name(first), first
            assert first.startswith("pdf/") and first.endswith(".pdf"), first
            assert os.path.isfile(blob_path(first))
            assert len(os.listdir(os.path.join(root, "pdf"))) == 1, "must not duplicate"

            other = store_bytes(b'{"a": 1}', "json")
            assert other.startswith("json/") and other != first

            # A truncated leftover is not "already stored".
            open(blob_path(first), "wb").close()
            assert not usable(blob_path(first))
            assert store_bytes(b"%PDF-1.4 hello", "pdf") == first
            assert usable(blob_path(first)), "empty stub must be rewritten"

            try:
                store_bytes(b"x", "docx")
            except ValueError:
                pass
            else:  # pragma: no cover
                raise AssertionError("unknown kind must raise")
        finally:
            runtime.UPLOAD_DIR = original
    print("blob_store: ok")


if __name__ == "__main__":
    demo()

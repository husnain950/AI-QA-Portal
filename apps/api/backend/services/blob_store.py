"""Content-addressed filesystem and private S3 storage.

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
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Optional, Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from backend import runtime
from backend.database import DatabaseConnection

SUFFIXES = {"pdf": ".pdf", "json": ".json", "evidence": ".zip", "render": ".png"}
_BLOB_NAME_RE = re.compile(r"^(pdf|json|evidence|render)/[0-9a-f]{64}\.(pdf|json|zip|png)$")
_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class BlobStat:
    size: int
    etag: str
    content_type: str


class StorageBackend(Protocol):
    def ready(self) -> None: ...

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None: ...

    def put_file(self, key: str, source: str | os.PathLike, *, content_type: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def stat(self, key: str) -> BlobStat: ...

    def read_range(self, key: str, start: int, end: int) -> bytes: ...

    def iter_range(self, key: str, start: int, end: int) -> Iterator[bytes]: ...

    def delete(self, key: str) -> bool: ...

    def copy(self, source_key: str, destination_key: str, *, content_type: str) -> None: ...

    def materialize(self, key: str) -> str: ...


def _content_type(kind_or_key: str) -> str:
    if kind_or_key == "pdf" or kind_or_key.endswith(".pdf"):
        return "application/pdf"
    if kind_or_key == "evidence" or kind_or_key.endswith(".zip"):
        return "application/zip"
    if kind_or_key == "render" or kind_or_key.endswith(".png"):
        return "image/png"
    return "application/json"


class FilesystemStorage:
    def ready(self) -> None:
        os.makedirs(upload_root(), exist_ok=True)
        if not os.access(upload_root(), os.R_OK | os.W_OK):
            raise RuntimeError("filesystem blob root is not readable and writable")

    def _path(self, key: str) -> str:
        return os.path.join(upload_root(), key)

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        del content_type
        _commit(self._path(key), lambda staged: _write_bytes(staged, data))

    def put_file(self, key: str, source: str | os.PathLike, *, content_type: str) -> None:
        del content_type
        _commit(self._path(key), lambda staged: shutil.copy2(source, staged))

    def exists(self, key: str) -> bool:
        return usable(self._path(key))

    def stat(self, key: str) -> BlobStat:
        path = self._path(key)
        if not usable(path):
            raise FileNotFoundError(key)
        return BlobStat(os.path.getsize(path), sha256_file(path), _content_type(key))

    def read_range(self, key: str, start: int, end: int) -> bytes:
        path = self._path(key)
        with open(path, "rb") as source:
            source.seek(start)
            return source.read(end - start + 1)

    def iter_range(self, key: str, start: int, end: int) -> Iterator[bytes]:
        remaining = end - start + 1
        with open(self._path(key), "rb") as source:
            source.seek(start)
            while remaining:
                chunk = source.read(min(_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if not os.path.exists(path):
            return False
        os.remove(path)
        return True

    def copy(self, source_key: str, destination_key: str, *, content_type: str) -> None:
        del content_type
        _commit(self._path(destination_key), lambda staged: shutil.copy2(self._path(source_key), staged))

    def materialize(self, key: str) -> str:
        return self._path(key)


class S3Storage:
    """Private S3-compatible storage, including Northflank's MinIO addon."""

    def __init__(self) -> None:
        endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip()
        if not endpoint:
            raise RuntimeError("S3_ENDPOINT_URL is required when STORAGE_BACKEND=s3")
        self.bucket = os.environ.get("S3_BUCKET", "crx-blobs")
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID") or os.environ.get("MINIO_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY") or os.environ.get("MINIO_SECRET_KEY"),
            region_name=os.environ.get("S3_REGION", "us-east-1"),
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ready(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        if self.exists(key):
            return
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
            Metadata={"sha256": _digest_from_key(key)},
        )

    def put_file(self, key: str, source: str | os.PathLike, *, content_type: str) -> None:
        if self.exists(key):
            return
        with open(source, "rb") as body:
            self.client.upload_fileobj(
                body,
                self.bucket,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    "CacheControl": "public, max-age=31536000, immutable",
                    "Metadata": {"sha256": _digest_from_key(key)},
                },
            )

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise

    def stat(self, key: str) -> BlobStat:
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                raise FileNotFoundError(key) from exc
            raise
        digest = response.get("Metadata", {}).get("sha256") or _digest_from_key(key)
        return BlobStat(
            int(response["ContentLength"]),
            digest,
            response.get("ContentType") or _content_type(key),
        )

    def read_range(self, key: str, start: int, end: int) -> bytes:
        response = self.client.get_object(
            Bucket=self.bucket,
            Key=key,
            Range=f"bytes={start}-{end}",
        )
        return response["Body"].read()

    def iter_range(self, key: str, start: int, end: int) -> Iterator[bytes]:
        response = self.client.get_object(
            Bucket=self.bucket,
            Key=key,
            Range=f"bytes={start}-{end}",
        )
        body = response["Body"]
        try:
            yield from body.iter_chunks(chunk_size=_CHUNK)
        finally:
            body.close()

    def delete(self, key: str) -> bool:
        if not self.exists(key):
            return False
        self.client.delete_object(Bucket=self.bucket, Key=key)
        cached = os.path.join(upload_root(), ".cache", key)
        if os.path.isfile(cached):
            os.remove(cached)
        return True

    def copy(self, source_key: str, destination_key: str, *, content_type: str) -> None:
        if self.exists(destination_key):
            return
        self.client.copy_object(
            Bucket=self.bucket,
            Key=destination_key,
            CopySource={"Bucket": self.bucket, "Key": source_key},
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
            Metadata={"sha256": _digest_from_key(destination_key)},
            MetadataDirective="REPLACE",
        )

    def materialize(self, key: str) -> str:
        destination = os.path.join(upload_root(), ".cache", key)
        if usable(destination):
            return destination
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        staged = f"{destination}.{os.getpid()}.staging"
        try:
            self.client.download_file(self.bucket, key, staged)
            os.replace(staged, destination)
        finally:
            if os.path.exists(staged):
                os.remove(staged)
        return destination


_storage: StorageBackend | None = None
_storage_signature: tuple[str, ...] | None = None


def get_storage() -> StorageBackend:
    global _storage, _storage_signature
    backend = os.environ.get("STORAGE_BACKEND", "filesystem").strip().lower()
    signature = (
        backend,
        upload_root(),
        os.environ.get("S3_ENDPOINT_URL", ""),
        os.environ.get("S3_BUCKET", "crx-blobs"),
        os.environ.get("S3_ACCESS_KEY_ID", ""),
        os.environ.get("MINIO_ACCESS_KEY", ""),
    )
    if _storage is None or signature != _storage_signature:
        if backend == "filesystem":
            _storage = FilesystemStorage()
        elif backend == "s3":
            _storage = S3Storage()
        else:
            raise RuntimeError(f"unsupported STORAGE_BACKEND: {backend}")
        _storage_signature = signature
    return _storage


def _digest_from_key(key: str) -> str:
    match = _BLOB_NAME_RE.match(key or "")
    return key.split("/", 1)[1].split(".", 1)[0] if match else hashlib.sha256(key.encode()).hexdigest()


def upload_root() -> str:
    return runtime.UPLOAD_DIR


def blob_path(rel_name: str) -> str:
    """Materialize a stored name and return a local path for parser compatibility."""
    return get_storage().materialize(rel_name)


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
    get_storage().put_bytes(name, data, content_type=_content_type(kind))
    return name


def store_file(source: str | os.PathLike, kind: str) -> str:
    """Copy a file into the store and return its name relative to ``UPLOAD_DIR``."""
    if kind not in SUFFIXES:
        raise ValueError(f"unknown blob kind: {kind}")
    name = rel_name(kind, sha256_file(source))
    get_storage().put_file(name, source, content_type=_content_type(kind))
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
    directory = os.path.join(upload_root(), ".staging", kind)
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
        get_storage().put_file(name, staged, content_type=_content_type(kind))
        os.remove(staged)
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
    db: DatabaseConnection,
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
    db: DatabaseConnection,
    name: Optional[str],
    *,
    ignore_document_id: Optional[str] = None,
) -> bool:
    """Remove a stored blob when nothing references it. Never raises."""
    if not name:
        return False
    if await is_referenced(db, name, ignore_document_id=ignore_document_id):
        return False
    try:
        return get_storage().delete(name)
    except OSError:
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

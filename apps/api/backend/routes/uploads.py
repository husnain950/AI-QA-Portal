"""Same-origin, immutable, range-capable blob proxy.

The object store remains private. Browsers and PDF.js continue to use the stable
``/uploads/{content-addressed-key}`` URL that the filesystem deployment exposed.
"""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from backend.services import blob_store

router = APIRouter(tags=["uploads"])
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _bounds(value: str | None, size: int) -> tuple[int, int, bool]:
    if not value:
        return 0, size - 1, False
    match = _RANGE.fullmatch(value.strip())
    if not match or size <= 0:
        raise HTTPException(status_code=416, detail="invalid byte range")
    first, last = match.groups()
    if not first:
        suffix = int(last or "0")
        if suffix <= 0:
            raise HTTPException(status_code=416, detail="invalid byte range")
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        raise HTTPException(
            status_code=416,
            detail="byte range is outside the object",
            headers={"Content-Range": f"bytes */{size}"},
        )
    return start, end, True


@router.api_route("/uploads/{key:path}", methods=["GET", "HEAD"])
async def download_blob(
    key: str,
    request: Request,
    range_header: str | None = Header(default=None, alias="Range"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    if not blob_store.is_blob_name(key):
        raise HTTPException(status_code=404, detail="blob not found")
    storage = blob_store.get_storage()
    try:
        stat = await asyncio.to_thread(storage.stat, key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="blob not found") from exc

    etag = f'"{stat.etag}"'
    common = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
    }
    if if_none_match and if_none_match.strip() in {etag, stat.etag, "*"}:
        return Response(status_code=304, headers=common)

    start, end, partial = _bounds(range_header, stat.size)
    headers = {
        **common,
        "Content-Length": str(end - start + 1),
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{stat.size}"
    status = 206 if partial else 200
    if request.method == "HEAD":
        return Response(status_code=status, media_type=stat.content_type, headers=headers)
    return StreamingResponse(
        storage.iter_range(key, start, end),
        status_code=status,
        media_type=stat.content_type,
        headers=headers,
    )

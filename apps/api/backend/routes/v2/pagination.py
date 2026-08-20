from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

from fastapi import HTTPException


def refreshed_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode_cursor(offset: int, fingerprint: str) -> str:
    payload = json.dumps({"offset": offset, "filter": fingerprint}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None, fingerprint: str) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload.get("filter") != fingerprint:
            raise ValueError("cursor filters changed")
        offset = int(payload["offset"])
        if offset < 0:
            raise ValueError("negative cursor")
        return offset
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid or stale cursor") from exc

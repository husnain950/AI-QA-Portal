"""X-Reviewer header — attribution record, not authentication."""

from __future__ import annotations

from fastapi import Header, HTTPException


async def require_reviewer(
    x_reviewer: str | None = Header(default=None, alias="X-Reviewer"),
) -> str:
    actor = (x_reviewer or "").strip()
    if not actor:
        raise HTTPException(
            status_code=400,
            detail="X-Reviewer header is required (record, not authentication)",
        )
    return actor

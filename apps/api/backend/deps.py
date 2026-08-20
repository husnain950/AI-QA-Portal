"""The authenticated actor for a request.

The name comes from the session the middleware resolved, so a client cannot choose who
its changes are attributed to. Service and route functions called directly (tests, CLI
tools) pass ``actor`` themselves.
"""

from __future__ import annotations

from fastapi import HTTPException, Request


async def require_reviewer(request: Request) -> str:
    actor = getattr(request.state, "actor", None)
    if not actor:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "sign in to use this API"},
        )
    return actor


async def require_admin(request: Request) -> str:
    """For the rare route that needs the role in its own body as well."""
    if getattr(request.state, "role", None) != "admin":
        raise HTTPException(
            status_code=403, detail={"code": "forbidden", "required_role": "admin"}
        )
    return await require_reviewer(request)

"""The authenticated actor for a request.

The name comes from the session the middleware resolved, so a client cannot choose who
its changes are attributed to. Service and route functions called directly (tests, CLI
tools) pass ``actor`` themselves.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from backend.database import DatabaseConnection
from backend.services import jobs


async def require_reviewer(request: Request) -> str:
    actor = getattr(request.state, "actor", None)
    if not actor:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "sign in to use this API"},
        )
    return actor


async def require_worker(db: DatabaseConnection) -> None:
    """503 unless a worker has beaten recently.

    Every enqueue route calls it: a job row written with nothing to claim it is not a
    slow job, it is a job that never runs, and the caller polls it until it times out.

    Called inline immediately before ``jobs.enqueue`` rather than declared as a
    ``Depends``, so a route's own validation still answers first -- an unmounted corpus
    should say so, not blame the worker.
    """
    if not await jobs.worker_online(db):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "worker_offline",
                "message": (
                    "no worker is running, so background jobs cannot be processed; "
                    "check /health/worker"
                ),
            },
        )


#: Tables `ensure_exists` may probe. An allowlist rather than a formatted parameter,
#: because the table name cannot be bound as a query parameter and every caller passes
#: a literal anyway.
_EXISTS_TABLES = frozenset({"documents", "sections", "footnotes", "annotations"})


async def ensure_exists(
    db: DatabaseConnection, table: str, row_id, detail: str
) -> None:
    """404 unless ``table`` has a row with this id.

    Seven handlers wrote this out longhand -- the same SELECT 1, the same fetchone
    check -- and the message casing had already drifted across the v1/v2 seam. The
    message stays a caller's argument so no client-visible text changes here.
    """
    if table not in _EXISTS_TABLES:
        raise ValueError(f"ensure_exists: unknown table {table!r}")
    async with db.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail=detail)

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.database import database_connection
from backend.middleware.security import SecurityMiddleware
from backend.routes import (
    ai_fixes,
    annotations,
    auth,
    corpus,
    documents,
    export,
    findings,
    footnotes,
    search,
    sections,
    timeline,
    uploads,
    variants,
)
from backend.routes.v2 import governance as v2_governance
from backend.routes.v2 import jobs as v2_jobs
from backend.routes.v2 import library as v2_library
from backend.routes.v2 import operations as v2_operations
from backend.routes.v2 import review as v2_review
from backend.routes.v2 import uploads as v2_uploads
from backend.runtime import UPLOAD_DIR, bootstrap_runtime
from backend.services import blob_store

os.makedirs(UPLOAD_DIR, exist_ok=True)

_DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
]

_raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
_origins = [o.strip() for o in _raw.split(",") if o.strip()] if _raw else _DEFAULT_ORIGINS


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await bootstrap_runtime()
    yield


app = FastAPI(title="FBR Corpus Platform API", lifespan=lifespan)

app.add_middleware(SecurityMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(sections.router, prefix="/api")
app.include_router(annotations.router, prefix="/api")
app.include_router(footnotes.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(corpus.router, prefix="/api")
app.include_router(findings.router, prefix="/api")
app.include_router(variants.router, prefix="/api")
app.include_router(timeline.router, prefix="/api")
app.include_router(ai_fixes.router, prefix="/api")
app.include_router(v2_library.router, prefix="/api/v2")
app.include_router(v2_operations.router, prefix="/api/v2")
app.include_router(v2_jobs.router, prefix="/api/v2")
app.include_router(v2_governance.router, prefix="/api/v2")
app.include_router(v2_review.router, prefix="/api/v2")
app.include_router(v2_uploads.router, prefix="/api/v2")

app.include_router(uploads.router)


@app.get("/health/live")
async def health_live():
    return {"status": "ok"}


async def _ready_payload():
    try:
        async with database_connection() as db:
            async with db.execute("SELECT version_num FROM alembic_version") as cur:
                schema = (await cur.fetchone())[0]
        await asyncio.to_thread(blob_store.get_storage().ready)
        return {"status": "ok", "db": "ok", "storage": "ok", "schema": schema}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "detail": str(exc)},
        )


@app.get("/health/ready")
async def health_ready():
    return await _ready_payload()


@app.get("/health/worker")
async def health_worker():
    try:
        async with database_connection() as db:
            async with db.execute(
                """
                SELECT worker_id, heartbeat_at, state, job_id
                FROM worker_heartbeats
                ORDER BY heartbeat_at DESC
                LIMIT 1
                """
            ) as cur:
                row = await cur.fetchone()
        if not row:
            raise RuntimeError("no worker heartbeat")
        heartbeat = datetime.fromisoformat(row["heartbeat_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - heartbeat > timedelta(seconds=30):
            raise RuntimeError("worker heartbeat is stale")
        return {"status": "ok", **dict(row)}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "degraded", "detail": str(exc)})


@app.get("/health")
async def health_check():
    """Compatibility alias for one release."""
    return await _ready_payload()

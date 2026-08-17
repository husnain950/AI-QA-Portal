import os
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.database import DB_PATH
from backend.routes import (
    ai_fixes,
    annotations,
    corpus,
    documents,
    export,
    findings,
    footnotes,
    search,
    sections,
    timeline,
    variants,
)
from backend.runtime import UPLOAD_DIR, bootstrap_runtime

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/health")
async def health_check():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1") as cur:
                await cur.fetchone()
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": "error", "detail": str(exc)},
        )

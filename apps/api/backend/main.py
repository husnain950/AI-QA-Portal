from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routes import (
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await bootstrap_runtime()
    yield


app = FastAPI(title="FBR Corpus Platform API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/health")
def health_check():
    return {"status": "ok"}

"""CRX PostgreSQL worker service."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import traceback
from datetime import datetime, timezone

from backend.database import database_connection, init_db
from backend.services import jobs

logger = logging.getLogger("crx.worker")
WORKER_ID = os.environ.get("WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"
STARTED_AT = datetime.now(timezone.utc).isoformat()


async def _beat(state: str, job_id: str | None = None) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    async with database_connection() as db:
        await db.execute(
            """
            INSERT INTO worker_heartbeats
                (worker_id, started_at, heartbeat_at, state, job_id, version)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (worker_id) DO UPDATE SET heartbeat_at = excluded.heartbeat_at,
                state = excluded.state, job_id = excluded.job_id, version = excluded.version
            """,
            (WORKER_ID, STARTED_AT, timestamp, state, job_id, os.environ.get("CRX_VERSION", "dev")),
        )
        await db.commit()


async def _execute(job: dict) -> dict:
    payload = job["payload"] or {}
    if job["type"] == "corpus_sync":
        from backend.services.corpus_sync import run_corpus_sync

        # `only` is what routes.corpus puts in the payload; the *_only flags are read
        # too so a job enqueued before this change still runs the corpora it meant.
        return await run_corpus_sync(
            only=payload.get("only"),
            dry_run=bool(payload.get("dry_run", False)),
            metrics=bool(payload.get("metrics", True)),
            ordinance_only=bool(payload.get("ordinance_only", False)),
            acts_only=bool(payload.get("acts_only", False)),
            rules_only=bool(payload.get("rules_only", False)),
        )
    if job["type"] == "detectors":
        from backend.services.findings_store import run_detectors_and_store

        async with database_connection() as db:
            result = await run_detectors_and_store(db, seed_flags=bool(payload.get("seed_flags", True)))
            await db.commit()
            return result
    if job["type"] == "provenance_scan":
        from backend.services import blob_store
        from backend.services.document_provenance import backfill_provenance_row

        changed = 0
        async with database_connection() as db:
            async with db.execute(
                "SELECT id, pdf_filename, json_filename, total_pages, provenance FROM documents ORDER BY id"
            ) as cur:
                rows = await cur.fetchall()
            for index, row in enumerate(rows, 1):
                if await jobs.heartbeat(db, job["id"], WORKER_ID, current=index, total=len(rows)):
                    raise asyncio.CancelledError
                result = await backfill_provenance_row(
                    db,
                    document_id=row["id"],
                    json_filename=row["json_filename"],
                    total_pages=row["total_pages"],
                    existing_raw=row["provenance"],
                    pdf_path=blob_store.blob_path(row["pdf_filename"]),
                    force_native_reinfer=bool(payload.get("force", False)),
                )
                changed += int(result is not None)
                await db.commit()
        return {"processed": len(rows), "derived": changed}
    if job["type"] in {"export", "regression_bundle"}:
        from backend.services.evidence import (
            build_document_bundle,
            build_regression_bundle,
        )

        async with database_connection() as db:
            if job["type"] == "export":
                return await build_document_bundle(db, payload["document_id"])
            return await build_regression_bundle(db, int(payload["finding_id"]))
    if job["type"] == "ai_proposal":
        from backend.services.ai_fix import create_proposal

        async with database_connection() as db:
            row = await create_proposal(
                db,
                payload["document_id"],
                payload["section_id"],
                payload["instructions"],
                actor=job["actor"],
                model=payload.get("model"),
            )
            await db.commit()
            return {"proposal_id": row["id"], "status": row["status"]}
    if job["type"] == "render_pdf":
        import io

        import pypdfium2 as pdfium

        from backend.services import blob_store

        async with database_connection() as db:
            async with db.execute(
                "SELECT pdf_filename FROM documents WHERE id = ?", (payload["document_id"],)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                raise KeyError(payload["document_id"])
        pdf = pdfium.PdfDocument(blob_store.blob_path(row["pdf_filename"]))
        page_number = int(payload["page"])
        if page_number < 1 or page_number > len(pdf):
            raise ValueError("page outside PDF")
        image = pdf[page_number - 1].render(scale=float(payload.get("scale", 1.5))).to_pil()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        key = blob_store.store_bytes(buffer.getvalue(), "render")
        return {"key": key, "download_url": f"/uploads/{key}", "page": page_number}
    raise ValueError(f"job handler not implemented for {job['type']}")


async def run() -> None:
    await init_db()
    await _beat("idle")
    while True:
        async with database_connection() as db:
            job = await jobs.claim(db, WORKER_ID)
        if not job:
            await _beat("idle")
            await asyncio.sleep(1)
            continue
        await _beat("running", job["id"])
        try:
            result = await _execute(job)
            async with database_connection() as db:
                await jobs.succeed(db, job["id"], result)
            await _beat("idle")
        except asyncio.CancelledError:
            async with database_connection() as db:
                await jobs.mark_cancelled(db, job["id"])
            await _beat("idle")
        except Exception as exc:
            logger.exception("job failed", extra={"job_id": job["id"], "job_type": job["type"]})
            async with database_connection() as db:
                await jobs.fail(
                    db,
                    job,
                    {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc(limit=20)},
                    transient=not isinstance(exc, (ValueError, KeyError)),
                )
            await _beat("idle")


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    asyncio.run(run())

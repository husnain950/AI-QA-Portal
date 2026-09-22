"""Corpus sync status and trigger endpoints for the portal dashboard."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database import DatabaseConnection, get_db
from backend.deps import require_reviewer, require_worker
from backend.services import jobs
from backend.services.corpus_registry import CORPORA, LABELS

router = APIRouter(prefix="/corpus", tags=["corpus"])

class CorpusMount(BaseModel):
    label: str
    title: str
    path: str
    # Pipeline-mount health (dir + output/*.json), not document count.
    configured: bool
    documents: int = 0


class CorpusStatus(BaseModel):
    #: One entry per registered corpus, in registry order. Clients should read this
    #: rather than the flat fields below, which exist only so an older frontend keeps
    #: working and are not extended for new corpora.
    corpora: List[CorpusMount] = []
    ordinance_path: str
    acts_path: str
    ordinance_configured: bool
    acts_configured: bool
    last_sync_at: Optional[str] = None
    last_status: Optional[str] = None
    ordinance_docs: int = 0
    acts_docs: int = 0
    total_documents: int = 0
    sync_running: bool = False
    last_summary: Optional[Dict[str, Any]] = None


class SyncRequest(BaseModel):
    dry_run: bool = False
    metrics: bool = True
    #: Registry labels to sync; empty or absent means all of them.
    only: Optional[List[str]] = None
    ordinance_only: bool = False
    acts_only: bool = False
    rules_only: bool = False

    def wanted(self) -> List[str]:
        """The corpora this request selects, validated against the registry."""
        if self.only:
            unknown = sorted(set(self.only) - set(LABELS))
            if unknown:
                raise HTTPException(
                    status_code=400,
                    detail=f"unknown corpus: {', '.join(unknown)}",
                )
            return [label for label in LABELS if label in set(self.only)]
        flagged = [
            label
            for label, flag in (
                ("ordinance", self.ordinance_only),
                ("acts", self.acts_only),
                ("rules", self.rules_only),
            )
            if flag
        ]
        return flagged or list(LABELS)


@router.get("/status", response_model=CorpusStatus)
async def corpus_status(db: DatabaseConnection = Depends(get_db)):
    last_sync_at = last_status = None
    last_summary = None
    counts: Dict[str, int] = {}
    try:
        async with db.execute(
            "SELECT last_sync_at, last_status, last_summary, "
            "ordinance_docs, acts_docs, rules_docs "
            "FROM corpus_sync_state WHERE id = 1"
        ) as cur:
            row = await cur.fetchone()
        if row:
            last_sync_at = row[0]
            last_status = row[1]
            if row[2]:
                try:
                    last_summary = json.loads(row[2])
                except json.JSONDecodeError:
                    last_summary = None
            counts = {
                "ordinance": int(row[3] or 0),
                "acts": int(row[4] or 0),
                "rules": int(row[5] or 0),
            }
    except Exception:
        pass

    async with db.execute("SELECT COUNT(*) FROM documents") as cur:
        total = (await cur.fetchone())[0]
    async with db.execute(
        "SELECT COUNT(*) FROM jobs WHERE type = 'corpus_sync' AND state IN ('queued','running')"
    ) as cur:
        sync_running = bool((await cur.fetchone())[0])

    mounts = [
        CorpusMount(
            label=corpus.label,
            title=corpus.title,
            path=str(corpus.path()),
            configured=corpus.configured(),
            documents=counts.get(corpus.label, 0),
        )
        for corpus in CORPORA
    ]
    by_label = {m.label: m for m in mounts}

    return CorpusStatus(
        corpora=mounts,
        # Flat fields for an older frontend. Deliberately not grown per corpus --
        # `corpora` above is the list to read.
        ordinance_path=by_label["ordinance"].path,
        acts_path=by_label["acts"].path,
        ordinance_configured=by_label["ordinance"].configured,
        acts_configured=by_label["acts"].configured,
        last_sync_at=last_sync_at,
        last_status=last_status,
        ordinance_docs=by_label["ordinance"].documents,
        acts_docs=by_label["acts"].documents,
        total_documents=int(total or 0),
        sync_running=sync_running,
        last_summary=last_summary,
    )


@router.post("/sync", status_code=202)
async def trigger_sync(
    body: SyncRequest = SyncRequest(),
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    wanted = body.wanted()
    missing = [c for c in CORPORA if c.label in wanted and not c.configured()]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="; ".join(
                f"{c.title} pipeline mount not on this host "
                f"(need output/*.json at {c.path()})"
                for c in missing
            ),
        )

    payload = body.model_dump()
    payload["only"] = wanted
    await require_worker(db)
    job = await jobs.enqueue(db, "corpus_sync", payload=payload, actor=actor)
    await db.commit()
    return {"job_id": job["id"], "state": job["state"]}


# Deleting a document cascades through every table that carries a real foreign key to
# it. These five do not: findings, section_overlays and jobs name a document by bare
# text, review_assignments names a finding, and a statute family outlives its last
# edition. They are swept here rather than from the delete route because a sweep is
# cheap, idempotent, and correct even for rows orphaned by an earlier delete.
#
# review_events is deliberately absent: `review_events_no_delete` (0001_postgres_baseline)
# rejects DELETE on an append-only audit log, so its rows are reported, never removed.
_ORPHAN_SWEEPS: List[tuple[str, str]] = [
    (
        "findings",
        "DELETE FROM findings f WHERE NOT EXISTS ("
        "SELECT 1 FROM documents d WHERE d.id = f.document_id)",
    ),
    # An overlay is keyed by the PDF's hash, which is how the blob is named.
    (
        "section_overlays",
        "DELETE FROM section_overlays o WHERE NOT EXISTS ("
        "SELECT 1 FROM documents d WHERE d.pdf_filename = 'pdf/' || o.pdf_sha256 || '.pdf')",
    ),
    # After findings, so assignments to findings deleted just above go too.
    (
        "review_assignments",
        "DELETE FROM review_assignments a WHERE NOT EXISTS ("
        "SELECT 1 FROM findings f WHERE f.id = a.finding_id)",
    ),
    (
        "jobs",
        "DELETE FROM jobs j WHERE j.payload ->> 'document_id' IS NOT NULL "
        "AND NOT EXISTS ("
        "SELECT 1 FROM documents d WHERE d.id = j.payload ->> 'document_id')",
    ),
    (
        "statute_families",
        "DELETE FROM statute_families s WHERE NOT EXISTS ("
        "SELECT 1 FROM documents d WHERE d.statute_family_id = s.id)",
    ),
]


@router.delete("/orphans")
async def purge_orphans(db: DatabaseConnection = Depends(get_db)):
    """Delete rows whose document is already gone.

    Admin-only for free: `required_role` gives every DELETE under /api the admin role,
    so this needs no dependency of its own.
    """
    deleted: Dict[str, int] = {}
    try:
        for table, sql in _ORPHAN_SWEEPS:
            async with db.execute(sql) as cursor:
                deleted[table] = max(cursor.rowcount, 0)
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="orphan purge failed")

    async with db.execute("SELECT COUNT(*) FROM review_events") as cursor:
        retained = (await cursor.fetchone())[0]

    return {
        "deleted": deleted,
        "retained": {"review_events": int(retained or 0)},
    }

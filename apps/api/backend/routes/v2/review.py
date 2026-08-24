"""Atomic triage, persistent review sessions, and renewable review leases."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend.database import DatabaseConnection, get_db, json_column
from backend.deps import require_reviewer
from backend.services import events, findings_store, review_state
from backend.services.clock import utc_now as _now
from backend.services.disposition import normalize_finding_triage

router = APIRouter(tags=["v2-review"])




class BulkItem(BaseModel):
    id: int
    triage: str
    expected_prior: str
    note: str | None = None


class BulkRequest(BaseModel):
    items: list[BulkItem] = Field(min_length=1, max_length=500)


@router.post("/findings/bulk-triage")
async def bulk_triage(
    body: BulkRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    key = idempotency_key.strip()
    if not key or len(key) > 200:
        raise HTTPException(status_code=400, detail="invalid Idempotency-Key")
    canonical = body.model_dump(mode="json")
    request_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    async with db.execute(
        "SELECT request_hash, response FROM bulk_idempotency WHERE key = ?", (key,)
    ) as cur:
        prior = await cur.fetchone()
    if prior:
        if prior["request_hash"] != request_hash:
            raise HTTPException(status_code=409, detail="idempotency key was used for another request")
        return json_column(prior["response"])

    ids = [item.id for item in body.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="finding IDs must be unique")
    placeholders = ",".join("?" for _ in ids)
    async with db.execute(
        f"SELECT * FROM findings WHERE id IN ({placeholders}) FOR UPDATE", ids
    ) as cur:
        locked = {row["id"]: dict(row) for row in await cur.fetchall()}
    conflicts = []
    for item in body.items:
        row = locked.get(item.id)
        if row is None or row["triage"] != item.expected_prior:
            conflicts.append(
                {
                    "id": item.id,
                    "expected": item.expected_prior,
                    "current": row["triage"] if row else None,
                }
            )
    if conflicts:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "bulk_conflict", "conflicts": conflicts},
        )

    changed = []
    section_ids: set[str] = set()
    for item in body.items:
        triage = normalize_finding_triage(item.triage)
        await findings_store.triage_finding(
            db, item.id, triage=triage, note=item.note, actor=actor
        )
        changed.append({"id": item.id, "from": item.expected_prior, "to": triage})
        if locked[item.id].get("section_id"):
            section_ids.add(locked[item.id]["section_id"])
    for section_id in section_ids:
        await review_state.refresh_section(db, section_id)
    await events.record(
        db,
        actor=actor,
        action="bulk_finding_triage",
        detail={"idempotency_key": key, "changes": changed},
    )
    response = {"updated": changed, "count": len(changed)}
    await db.execute(
        """
        INSERT INTO bulk_idempotency (key, actor, request_hash, response, created_at)
        VALUES (?, ?, ?, CAST(? AS jsonb), ?)
        """,
        (key, actor, request_hash, json.dumps(response), _now().isoformat()),
    )
    await db.commit()
    return response


class SessionCreate(BaseModel):
    client_session_id: str = Field(min_length=1, max_length=200)
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: str = "risk_desc"
    finding_id: int | None = None


async def _next_finding(
    db: DatabaseConnection,
    session,
    exclude: list[int] | None = None,
) -> int | None:
    filters = json_column(session["filters"])
    clauses = ["first_seen_at <= ?", "triage = 'new'"]
    params: list = [session["snapshot_at"]]
    for key, column in (("detector", "detector"), ("document_id", "document_id"), ("severity", "severity")):
        if filters.get(key):
            clauses.append(f"{column} = ?")
            params.append(filters[key])
    if exclude:
        placeholders = ",".join("?" for _ in exclude)
        clauses.append(f"id NOT IN ({placeholders})")
        params.extend(exclude)
    order = "CASE severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, score DESC NULLS LAST, id"
    async with db.execute(
        f"SELECT id FROM findings WHERE {' AND '.join(clauses)} ORDER BY {order} LIMIT 1",
        params,
    ) as cur:
        row = await cur.fetchone()
    return int(row["id"]) if row else None


async def _finding_ref(db: DatabaseConnection, finding_id: int | None) -> dict | None:
    if finding_id is None:
        return None
    async with db.execute(
        "SELECT id, document_id, section_id, triage FROM findings WHERE id = ?",
        (finding_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


def _history(session) -> list[int]:
    raw = session["cursor"]
    if not raw:
        return []
    try:
        return [int(value) for value in json.loads(raw)]
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


async def _session(db: DatabaseConnection, session_id: str):
    async with db.execute("SELECT * FROM review_sessions WHERE id = ?", (session_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="review session not found")
    return row


@router.post("/review-sessions", status_code=201)
async def create_session(
    body: SessionCreate,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    now = _now()
    session_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO review_sessions
            (id, actor, client_session_id, filters, sort, snapshot_at,
             current_finding_id, cursor, created_at, updated_at, expires_at)
        VALUES (?, ?, ?, CAST(? AS jsonb), ?, ?, NULL, NULL, ?, ?, ?)
        """,
        (
            session_id,
            actor,
            body.client_session_id,
            json.dumps(body.filters),
            body.sort,
            now.isoformat(),
            now.isoformat(),
            now.isoformat(),
            (now + timedelta(hours=24)).isoformat(),
        ),
    )
    row = await _session(db, session_id)
    finding_id = body.finding_id
    if finding_id is not None:
        async with db.execute(
            "SELECT id FROM findings WHERE id = ? AND first_seen_at <= ?",
            (finding_id, now.isoformat()),
        ) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="initial finding not found")
    else:
        finding_id = await _next_finding(db, row)
    await db.execute(
        "UPDATE review_sessions SET current_finding_id = ?, cursor = '[]' WHERE id = ?",
        (finding_id, session_id),
    )
    await db.commit()
    return {
        "id": session_id,
        "snapshot_at": now.isoformat(),
        "current_finding_id": finding_id,
        "current": await _finding_ref(db, finding_id),
    }


@router.get("/review-sessions/{session_id}")
async def resume_session(
    session_id: str,
    db: DatabaseConnection = Depends(get_db),
):
    row = await _session(db, session_id)
    payload = dict(row)
    payload["current"] = await _finding_ref(db, row["current_finding_id"])
    return payload


class AdvanceRequest(BaseModel):
    finding_id: int
    triage: str
    expected_prior: str = "new"
    note: str | None = None


@router.post("/review-sessions/{session_id}/advance")
async def advance_session(
    session_id: str,
    body: AdvanceRequest,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    session = await _session(db, session_id)
    if session["actor"] != actor:
        raise HTTPException(status_code=409, detail="review session belongs to another declared reviewer")
    async with db.execute("SELECT * FROM findings WHERE id = ? FOR UPDATE", (body.finding_id,)) as cur:
        finding = await cur.fetchone()
    if not finding or finding["triage"] != body.expected_prior:
        await db.rollback()
        raise HTTPException(status_code=409, detail={"code": "stale_finding"})
    await findings_store.triage_finding(
        db,
        body.finding_id,
        triage=body.triage,
        note=body.note,
        actor=actor,
    )
    await review_state.refresh_section(db, finding["section_id"])
    history = _history(session)
    if body.finding_id not in history:
        history.append(body.finding_id)
    next_id = await _next_finding(db, session, history)
    now = _now().isoformat()
    await db.execute(
        """
        UPDATE review_sessions
        SET current_finding_id = ?, cursor = ?, updated_at = ?
        WHERE id = ?
        """,
        (next_id, json.dumps(history), now, session_id),
    )
    await db.commit()
    return {
        "session_id": session_id,
        "previous_finding_id": body.finding_id,
        "current_finding_id": next_id,
        "current": await _finding_ref(db, next_id),
    }


@router.post("/review-sessions/{session_id}/next")
async def next_finding(
    session_id: str,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    session = await _session(db, session_id)
    if session["actor"] != actor:
        raise HTTPException(status_code=409, detail="review session belongs to another declared reviewer")
    history = _history(session)
    current = session["current_finding_id"]
    if current is not None and int(current) not in history:
        history.append(int(current))
    next_id = await _next_finding(db, session, history)
    await db.execute(
        "UPDATE review_sessions SET current_finding_id = ?, cursor = ?, updated_at = ? WHERE id = ?",
        (next_id, json.dumps(history), _now().isoformat(), session_id),
    )
    await db.commit()
    return {"session_id": session_id, "current_finding_id": next_id, "current": await _finding_ref(db, next_id)}


@router.post("/review-sessions/{session_id}/back")
async def previous_finding(
    session_id: str,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    session = await _session(db, session_id)
    if session["actor"] != actor:
        raise HTTPException(status_code=409, detail="review session belongs to another declared reviewer")
    history = _history(session)
    previous_id = history.pop() if history else None
    await db.execute(
        "UPDATE review_sessions SET current_finding_id = ?, cursor = ?, updated_at = ? WHERE id = ?",
        (previous_id, json.dumps(history), _now().isoformat(), session_id),
    )
    await db.commit()
    return {
        "session_id": session_id,
        "current_finding_id": previous_id,
        "current": await _finding_ref(db, previous_id),
    }


@router.delete("/review-sessions/{session_id}", status_code=204)
async def dispose_session(
    session_id: str,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    await db.execute("DELETE FROM review_sessions WHERE id = ? AND actor = ?", (session_id, actor))
    await db.commit()


class LeaseRequest(BaseModel):
    client_session_id: str = Field(min_length=1, max_length=200)


@router.post("/review-assignments/{finding_id}")
async def claim_assignment(
    finding_id: int,
    body: LeaseRequest,
    db: DatabaseConnection = Depends(get_db),
    actor: str = Depends(require_reviewer),
):
    now = _now()
    expires = now + timedelta(minutes=15)
    async with db.execute(
        "SELECT * FROM review_assignments WHERE finding_id = ? FOR UPDATE", (finding_id,)
    ) as cur:
        existing = await cur.fetchone()
    if existing and existing["expires_at"] > now.isoformat() and (
        existing["actor"] != actor or existing["client_session_id"] != body.client_session_id
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "finding_leased", "actor": existing["actor"], "expires_at": existing["expires_at"]},
        )
    await db.execute(
        """
        INSERT INTO review_assignments (finding_id, actor, client_session_id, claimed_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (finding_id) DO UPDATE SET actor = excluded.actor,
            client_session_id = excluded.client_session_id,
            claimed_at = excluded.claimed_at, expires_at = excluded.expires_at
        """,
        (finding_id, actor, body.client_session_id, now.isoformat(), expires.isoformat()),
    )
    await db.commit()
    return {"finding_id": finding_id, "actor": actor, "expires_at": expires.isoformat()}

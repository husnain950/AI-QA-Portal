"""Unified Ordinance + Acts corpus sync (shared by CLI and API)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from backend.database import DB_PATH
from backend.sync_acts import run_sync


_REPO_ROOT = Path(__file__).resolve().parents[4]


def default_ordinance_path() -> Path:
    return Path(
        os.environ.get(
            "CORPUS_ORDINANCE",
            str(_REPO_ROOT / "data" / "corpora" / "ordinance"),
        )
    )


def default_acts_path() -> Path:
    return Path(
        os.environ.get(
            "CORPUS_ACTS",
            str(_REPO_ROOT / "data" / "corpora" / "acts"),
        )
    )


async def _record_sync(summary: Dict[str, Any], status: str) -> None:
    ordinance = int(summary.get("ordinance", {}).get("imported", 0) or 0) + int(
        summary.get("ordinance", {}).get("skipped", 0) or 0
    )
    acts = int(summary.get("acts", {}).get("imported", 0) or 0) + int(
        summary.get("acts", {}).get("skipped", 0) or 0
    )
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS corpus_sync_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_sync_at TEXT,
                    last_status TEXT,
                    last_summary TEXT,
                    ordinance_docs INTEGER DEFAULT 0,
                    acts_docs INTEGER DEFAULT 0
                );
                """
            )
            await db.execute("INSERT OR IGNORE INTO corpus_sync_state (id) VALUES (1);")
            async with db.execute("SELECT COUNT(*) FROM documents") as cur:
                total_corpus = (await cur.fetchone())[0]
            await db.execute(
                """
                UPDATE corpus_sync_state
                SET last_sync_at = ?, last_status = ?, last_summary = ?,
                    ordinance_docs = ?, acts_docs = ?
                WHERE id = 1
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    status,
                    json.dumps(summary, default=str),
                    ordinance,
                    acts,
                ),
            )
            await db.commit()
            summary["db_documents"] = total_corpus
    except Exception as err:
        summary["sync_state_error"] = str(err)


async def sync_one(
    label: str,
    repo: Path,
    *,
    dry_run: bool,
    force: bool,
    strict: bool,
    metrics: bool,
    pdf_dir: Optional[Path],
) -> Dict[str, Any]:
    if not repo.is_dir():
        return {
            "label": label,
            "repo": str(repo),
            "failed": 1,
            "error": f"corpus path does not exist: {repo}",
            "imported": 0,
            "skipped": 0,
            "unmatched": 0,
        }
    metrics_dir = (repo / "reports") if metrics else None
    result = await run_sync(
        repo,
        dry_run=dry_run,
        force=force,
        acts_repo=True,
        strict=strict,
        metrics_dir=metrics_dir,
        pdf_dir=pdf_dir,
    )
    result["label"] = label
    result["repo"] = str(repo)
    return result


async def run_corpus_sync(
    *,
    ordinance: Optional[Path] = None,
    acts: Optional[Path] = None,
    dry_run: bool = False,
    force: bool = False,
    strict: bool = False,
    metrics: bool = False,
    ordinance_only: bool = False,
    acts_only: bool = False,
) -> Dict[str, Any]:
    from backend.runtime import bootstrap_runtime

    await bootstrap_runtime()

    ordinance = (ordinance or default_ordinance_path()).expanduser().resolve()
    acts = (acts or default_acts_path()).expanduser().resolve()

    jobs: List[tuple[str, Path]] = []
    if not acts_only:
        jobs.append(("ordinance", ordinance))
    if not ordinance_only:
        jobs.append(("acts", acts))

    combined: Dict[str, Any] = {
        "ordinance": {},
        "acts": {},
        "failed": 0,
        "unmatched": 0,
    }
    for label, path in jobs:
        part = await sync_one(
            label,
            path,
            dry_run=dry_run,
            force=force,
            strict=strict,
            metrics=metrics,
            pdf_dir=None,
        )
        combined[label] = part
        combined["failed"] += int(part.get("failed", 0) or 0)
        combined["unmatched"] += int(part.get("unmatched", 0) or 0)
        if part.get("error"):
            combined["failed"] += 1

    status = "ok" if combined["failed"] == 0 else "failed"
    if not dry_run:
        await _record_sync(combined, status)
    return combined

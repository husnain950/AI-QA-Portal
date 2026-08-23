"""Corpus sync across every registered corpus (shared by CLI, API job and worker)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from backend.database import database_connection
from backend.services.corpus_registry import (  # noqa: F401  (re-exported)
    CORPORA,
    LABELS,
    Corpus,
    corpus_root_configured,
    get,
    selected,
)
from backend.sync_acts import run_sync


async def _record_sync(summary: Dict[str, Any], status: str) -> None:
    def _counted(label: str) -> int:
        part = summary.get(label) or {}
        return int(part.get("imported", 0) or 0) + int(part.get("skipped", 0) or 0)

    # ordinance_docs / acts_docs are columns; every corpus is also counted into the
    # JSON summary, so a new corpus needs no column of its own to be reported.
    summary["corpus_docs"] = {label: _counted(label) for label in LABELS}
    try:
        async with database_connection() as db:
            await db.execute(
                "INSERT INTO corpus_sync_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
            )
            async with db.execute("SELECT COUNT(*) FROM documents") as cur:
                total_corpus = (await cur.fetchone())[0]
            await db.execute(
                """
                UPDATE corpus_sync_state
                SET last_sync_at = ?, last_status = ?, last_summary = ?,
                    ordinance_docs = ?, acts_docs = ?, rules_docs = ?
                WHERE id = 1
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    status,
                    json.dumps(summary, default=str),
                    _counted("ordinance"),
                    _counted("acts"),
                    _counted("rules"),
                ),
            )
            await db.commit()
            summary["db_documents"] = total_corpus
    except Exception as err:
        summary["sync_state_error"] = str(err)


def source_key_collisions() -> Dict[str, list[str]]:
    """JSON stems claimed by more than one corpus, as ``{stem: [labels]}``.

    A document's identity is ``uuid5(..., "pdf-qa-portal:acts_corpus:<json stem>")``
    -- see ``sync_acts.deterministic_document_id``. ``SOURCE_TYPE`` is the same
    constant for every corpus, so the stem is a single global namespace: two corpora
    shipping ``Customs Rules, 2001.json`` would resolve to one ``documents`` row and
    each sync would overwrite the other, quietly, forever.

    Nothing collides today (checked across all three source trees), and the fix is not
    to re-key the id -- that would change the id of every document already reviewed.
    It is to notice. The check is a directory listing, and it covers every mounted
    corpus rather than only the selected ones: syncing Rules alone can still clobber an
    Acts document.
    """
    claimed: Dict[str, list[str]] = {}
    for corpus in CORPORA:
        output = corpus.path() / "output"
        if not output.is_dir():
            continue
        for json_path in output.glob("*.json"):
            claimed.setdefault(json_path.stem, []).append(corpus.label)
    return {
        stem: labels for stem, labels in claimed.items() if len(set(labels)) > 1
    }


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
        corpus_origin=label,
    )
    result["label"] = label
    result["repo"] = str(repo)
    return result


async def run_corpus_sync(
    *,
    ordinance: Optional[Path] = None,
    acts: Optional[Path] = None,
    rules: Optional[Path] = None,
    only: Optional[Iterable[str]] = None,
    dry_run: bool = False,
    force: bool = False,
    strict: bool = False,
    metrics: bool = False,
    ordinance_only: bool = False,
    acts_only: bool = False,
    rules_only: bool = False,
) -> Dict[str, Any]:
    """Sync the selected corpora.

    ``only`` is the registry-native selector. The ``*_only`` flags and the explicit
    path arguments predate it and are still honoured, because the CLI, the API request
    body and the worker payload all speak them.
    """
    from backend.runtime import bootstrap_runtime

    await bootstrap_runtime()

    overrides = {"ordinance": ordinance, "acts": acts, "rules": rules}
    flagged = [
        label
        for label, flag in (
            ("ordinance", ordinance_only),
            ("acts", acts_only),
            ("rules", rules_only),
        )
        if flag
    ]
    if only is None and flagged:
        only = flagged

    collisions = source_key_collisions()
    if collisions:
        raise ValueError(
            "the same JSON stem is claimed by more than one corpus, which would give "
            "both documents one id and make each sync overwrite the other: "
            + "; ".join(
                f"{stem!r} in {', '.join(sorted(set(labels)))}"
                for stem, labels in sorted(collisions.items())
            )
        )

    combined: Dict[str, Any] = {"failed": 0, "unmatched": 0}
    # Every registered corpus gets a key, selected or not, so a reader of the summary
    # can tell "synced nothing" from "was not asked to".
    for label in LABELS:
        combined[label] = {}

    # An explicit request must be honoured or refused; a blanket "sync everything" must
    # not fail because a corpus is not staged on this host. Without the distinction a
    # third corpus makes every default sync report failure everywhere it is absent --
    # CI, every deployment, and any checkout that has not vendored it yet.
    explicit = only is not None

    for corpus in selected(only):
        override = overrides.get(corpus.label)
        path = (override or corpus.path()).expanduser().resolve()
        if not explicit and not corpus_root_configured(path):
            combined[corpus.label] = {
                "label": corpus.label,
                "repo": str(path),
                "skipped_corpus": "not mounted on this host",
                "imported": 0,
                "skipped": 0,
                "unmatched": 0,
                "failed": 0,
            }
            continue
        part = await sync_one(
            corpus.label,
            path,
            dry_run=dry_run,
            force=force,
            strict=strict,
            metrics=metrics,
            # The registry names each corpus's source-PDF subdirectory (`Acts/`,
            # `Rules/`, or the root when it has none). Passing None here let
            # `_source_pdf_index` apply its own hardcoded `Acts/`-else-root rule to
            # every lane, so the Rules corpus only worked because the fallback
            # recursive scan happened to reach `Rules/` anyway.
            #
            # Derived from `path`, not from the registry: `path` may be an override
            # (`make seed-fixtures` syncs `data/fixtures/acts`), and reading the
            # registry here would point the sync at the real corpus instead.
            pdf_dir=corpus.source_within(path),
        )
        combined[corpus.label] = part
        # `sync_one` already counts an unusable corpus root as one failure and also
        # sets `error`; adding both counted it twice, so one missing directory
        # reported "failed: 2".
        failures = int(part.get("failed", 0) or 0)
        combined["failed"] += failures or (1 if part.get("error") else 0)
        combined["unmatched"] += int(part.get("unmatched", 0) or 0)

    status = "ok" if combined["failed"] == 0 else "failed"
    if not dry_run:
        await _record_sync(combined, status)
    return combined

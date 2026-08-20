"""Ingesting the Acts pipeline's own QA numbers against the active version."""

import json

import pytest

from backend.database import database_connection
from backend.services import acts_metrics
from backend.sync_acts import run_sync
from backend.tests.conftest import write_pair


def _reports(directory, *, invariants=True, conservation=True, stem="act"):
    directory.mkdir(parents=True, exist_ok=True)
    if invariants:
        (directory / acts_metrics.INVARIANTS_REPORT).write_text(
            json.dumps(
                {
                    f"/pipeline/output/{stem}.json": {
                        "invariants": [
                            {"name": "html_well_formed", "passed": True,
                             "failures": [], "n_failures": 0},
                            {"name": "no_bold_body_subsection_marker", "passed": False,
                             "failures": ["s.37C", "s.37E"], "n_failures": 3},
                        ],
                        "cases": [{"id": "A19", "passed": True}],
                        "known_gaps": [],
                        "skipped": [],
                    }
                }
            ),
            encoding="utf-8",
        )
    if conservation:
        (directory / acts_metrics.CONSERVATION_REPORT).write_text(
            json.dumps(
                {
                    "gates": {"body": 99.99, "footnote": 100.0},
                    "editions": [
                        {
                            "json": f"{stem}.json",
                            "body_conserved": 100.0,
                            "body_missing": 0,
                            "footnote_conserved": 99.843,
                            "footnote_missing": 135,
                            "passed": False,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
    return directory


@pytest.mark.asyncio
async def test_metrics_attach_to_the_active_version(runtime_sandbox):
    source = runtime_sandbox["root"] / "export"
    write_pair(source, name="act")
    await run_sync(source)

    reports = _reports(runtime_sandbox["root"] / "reports")
    async with database_connection() as db:
        result = await acts_metrics.ingest(db, reports)
        await db.commit()

        async with db.execute(
            """
            SELECT m.*, v.version_no, v.is_active
            FROM version_metrics m
            JOIN document_versions v ON v.id = m.version_id
            """
        ) as cursor:
            row = dict(await cursor.fetchone())

    assert result["status"] == "ok" and result["versions_updated"] == 1
    assert row["is_active"] == 1 and row["version_no"] == 1
    assert (row["invariants_passed"], row["invariants_total"]) == (1, 2)
    assert (row["cases_passed"], row["cases_total"]) == (1, 1)
    assert row["footnote_conserved"] == pytest.approx(99.843)
    assert row["footnote_missing"] == 135
    assert row["gate_ok"] == 0, "conservation fail AND a failing invariant"
    detail = json.loads(row["detail_json"])
    assert detail["failing_invariants"] == ["no_bold_body_subsection_marker"]
    assert detail["failures"]["no_bold_body_subsection_marker"] == ["s.37C", "s.37E"]


@pytest.mark.asyncio
async def test_ingest_is_idempotent_and_reingests_over_itself(runtime_sandbox):
    source = runtime_sandbox["root"] / "export"
    write_pair(source, name="act")
    await run_sync(source)
    reports = _reports(runtime_sandbox["root"] / "reports")

    async with database_connection() as db:
        await acts_metrics.ingest(db, reports)
        await db.commit()

        # A later run with a green report must overwrite, not accumulate.
        (reports / acts_metrics.CONSERVATION_REPORT).write_text(
            json.dumps(
                {
                    "editions": [
                        {
                            "json": "act.json",
                            "body_conserved": 100.0,
                            "body_missing": 0,
                            "footnote_conserved": 100.0,
                            "footnote_missing": 0,
                            "passed": True,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (reports / acts_metrics.INVARIANTS_REPORT).write_text(
            json.dumps(
                {
                    "/x/act.json": {
                        "invariants": [
                            {"name": "html_well_formed", "passed": True,
                             "failures": [], "n_failures": 0}
                        ],
                        "cases": [],
                    }
                }
            ),
            encoding="utf-8",
        )
        await acts_metrics.ingest(db, reports)
        await db.commit()

        async with db.execute("SELECT COUNT(*) FROM version_metrics") as cursor:
            assert (await cursor.fetchone())[0] == 1
        async with db.execute("SELECT gate_ok FROM version_metrics") as cursor:
            assert (await cursor.fetchone())[0] == 1


@pytest.mark.asyncio
async def test_absent_reports_are_a_skip_not_a_failure(runtime_sandbox):
    async with database_connection() as db:
        result = await acts_metrics.ingest(db, runtime_sandbox["root"] / "nowhere")
    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_editions_without_a_portal_document_are_reported_not_dropped(
    runtime_sandbox,
):
    source = runtime_sandbox["root"] / "export"
    write_pair(source, name="act")
    await run_sync(source)
    reports = _reports(runtime_sandbox["root"] / "reports", stem="some other edition")

    async with database_connection() as db:
        result = await acts_metrics.ingest(db, reports)

    assert result["versions_updated"] == 0
    assert result["unmatched"] == ["some other edition"]


@pytest.mark.asyncio
async def test_sync_can_ingest_metrics_in_the_same_run(runtime_sandbox):
    source = runtime_sandbox["root"] / "export"
    write_pair(source, name="act")
    reports = _reports(runtime_sandbox["root"] / "reports")

    summary = await run_sync(source, metrics_dir=reports)
    assert summary["added"] == 1
    assert summary["metrics"]["versions_updated"] == 1

    async with database_connection() as db:
        async with db.execute("SELECT COUNT(*) FROM version_metrics") as cursor:
            assert (await cursor.fetchone())[0] == 1

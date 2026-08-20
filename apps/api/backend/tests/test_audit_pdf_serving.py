import json
from pathlib import Path

import pytest

from backend import audit_pdf_serving
from backend.database import database_connection
from backend.sync_acts import run_sync
from backend.tests.conftest import write_pair


@pytest.mark.asyncio
async def test_audit_reports_ok_and_missing_file(runtime_sandbox):
    source = runtime_sandbox["root"] / "export"
    write_pair(source)
    await run_sync(source)

    async with database_connection() as db:
        ok_rows = await audit_pdf_serving.audit_documents(db)

    assert len(ok_rows) == 1
    assert ok_rows[0]["status"] == "ok"
    assert ok_rows[0]["page_count"] >= 1

    pdf = next(Path(runtime_sandbox["upload_dir"]).glob("pdf/*.pdf"))
    pdf.unlink()

    async with database_connection() as db:
        missing_rows = await audit_pdf_serving.audit_documents(db)

    assert missing_rows[0]["status"] == "missing_file"


def test_discover_source_pdf_gaps_marks_folders_without_pdf(tmp_path):
    good = tmp_path / "Has PDF"
    good.mkdir()
    (good / "act.pdf").write_bytes(b"%PDF-1.4")
    (good / "act.json").write_text("{}", encoding="utf-8")

    bad = tmp_path / "No PDF"
    bad.mkdir()
    (bad / "act.json").write_text("{}", encoding="utf-8")

    empty = tmp_path / "Empty PDF"
    empty.mkdir()
    (empty / "act.pdf").write_bytes(b"")
    (empty / "act.json").write_text("{}", encoding="utf-8")

    findings = audit_pdf_serving.discover_source_pdf_gaps(tmp_path)
    by_key = {item["source_key"]: item for item in findings}
    assert "Has PDF" not in by_key
    assert by_key["No PDF"]["reason"] == "no_pdf_in_sync_source"
    assert by_key["Empty PDF"]["reason"] == "empty_or_unusable_pdf_in_sync_source"
    assert json.loads(json.dumps(findings))  # JSON-serializable

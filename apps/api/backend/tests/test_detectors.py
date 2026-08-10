"""Tests for services/detectors.py — at least heading_only + fingerprint stability."""

import pytest
import pytest_asyncio
import aiosqlite

from backend.services.detectors import (
    DETECTOR_VERSION,
    Finding,
    _detect_heading_only,
    _detect_glyph_split,
    family_key,
    edition_date,
)
from backend.tests.conftest import runtime_sandbox


def test_family_key_strips_year():
    assert family_key("Customs Act, 1969") == "customs act"
    assert family_key("Income Tax Ordinance, 2001 (as amended)") == "income tax ordinance"
    assert family_key("Finance Act 2022") == "finance act"


def test_edition_date_extracts_year():
    assert edition_date("Customs Act, 1969") == "1969"
    assert edition_date("Finance Act 2022") == "2022"
    assert edition_date("No year here") is None


def test_fingerprint_stable_across_versions():
    """Fingerprint must not contain DETECTOR_VERSION as a structured component."""
    fp = "heading_only:sec-abc"
    parts = fp.split(":")
    assert DETECTOR_VERSION not in parts
    assert "score" not in fp


@pytest.mark.asyncio
async def test_heading_only_detector(runtime_sandbox):
    """Detect sections whose body is just the heading."""
    db_path = runtime_sandbox["db_path"]
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")

        await db.execute("""
            INSERT INTO documents (id, name, pdf_filename, json_filename, total_sections, total_pages, uploaded_at, status)
            VALUES ('doc-d', 'Test Act, 2020', 'test.pdf', 'test.json', 2, 1, '2026-01-01', 'pending')
        """)
        await db.execute("""
            INSERT INTO sections (id, document_id, section_code, section_heading, sort_order, review_status, plain_text, html_content)
            VALUES ('sec-h1', 'doc-d', '1', 'Short title', 1, 'pending', '1 Short title', '<p>1 Short title</p>')
        """)
        await db.execute("""
            INSERT INTO sections (id, document_id, section_code, section_heading, sort_order, review_status, plain_text, html_content)
            VALUES ('sec-h2', 'doc-d', '2', 'Definitions', 2, 'pending', 'This section has a much longer body that is clearly not just the heading', '<p>body</p>')
        """)
        await db.commit()

        findings = await _detect_heading_only(db)
        section_ids = [f[0] for f in findings]
        assert "sec-h1" in section_ids
        assert "sec-h2" not in section_ids


@pytest.mark.asyncio
async def test_glyph_split_detector(runtime_sandbox):
    """Detect OCR glyph split artifacts."""
    db_path = runtime_sandbox["db_path"]
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")

        await db.execute("""
            INSERT INTO documents (id, name, pdf_filename, json_filename, total_sections, total_pages, uploaded_at, status)
            VALUES ('doc-g', 'OCR Test Act, 2020', 'test.pdf', 'test.json', 1, 1, '2026-01-01', 'pending')
        """)
        await db.execute("""
            INSERT INTO sections (id, document_id, section_code, section_heading, sort_order, review_status, plain_text, html_content)
            VALUES ('sec-g1', 'doc-g', '3', 'Heading', 1, 'pending', 'This section was O mitted from the CHAP TER listing', '<p>body</p>')
        """)
        await db.commit()

        findings = await _detect_glyph_split(db)
        section_ids = [f[0] for f in findings]
        assert "sec-g1" in section_ids

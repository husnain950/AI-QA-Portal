"""Unit tests for structural parse-quality heuristics and store wiring."""

import json

from backend.database import database_connection
from backend.services.document_store import apply_parsed_document
from backend.services.json_parser import parse_json_document
from backend.services.parse_quality import (
    assess_section_quality,
    deserialize_quality_flags,
    serialize_quality_flags,
)
from backend.tests.conftest import sample_document


def _conclusion_style_body() -> str:
    """Finance Act Conclusion-style: single h4, glued footnotes, Table 6, no table."""
    # Keep well over the wall-of-text threshold inside one heading tag.
    filler = (
        "Tax-wise TAX Tax-wise Tax Base estimates7 Imports.8 PBS9 "
        "See Table 6 for the breakdown of revenue estimates. "
    ) * 25
    assert len(filler) > 800
    return (
        f'<h4 class="section-heading">Conclusion. {filler}</h4>',
        f"Conclusion. {filler}",
    )


def test_conclusion_style_leaf_flags_missing_table_glue_and_wall():
    html, plain = _conclusion_style_body()
    flags = assess_section_quality(
        html_content=html,
        plain_text=plain,
        section_heading="Conclusion",
    )
    codes = {flag["code"] for flag in flags}
    assert "missing_table" in codes
    assert "footnote_glue" in codes
    assert "wall_of_text" in codes
    for flag in flags:
        assert flag["reason"]


def test_clean_leaf_with_table_and_cite_has_no_flags():
    html = (
        "<p>Revenue is summarized below.<sup class=\"cite\">1</sup></p>"
        "<table><tr><td>Item</td><td>Amount</td></tr></table>"
        "<p>See Table 1 for details.</p>"
    )
    plain = "Revenue is summarized below.1 See Table 1 for details."
    flags = assess_section_quality(
        html_content=html,
        plain_text=plain,
        section_heading="Short heading",
    )
    assert flags == []


def test_heading_body_bleed_on_long_multi_sentence_heading():
    heading = (
        "This is a very long heading that has clearly absorbed body text. "
        "It contains a second sentence which should trigger the bleed heuristic."
    )
    flags = assess_section_quality(
        html_content="<p>Short body.</p>",
        plain_text="Short body.",
        section_heading=heading,
    )
    assert any(flag["code"] == "heading_body_bleed" for flag in flags)


def test_heading_body_bleed_on_page_furniture_below_the_length_floor():
    """A SHORT heading that has swallowed page furniture must still flag.

    Length alone cannot find this class.  Measured over 15,960 corpus headings:
    the longest CLEAN heading is 172 chars while corrupt ones start at 21, so the
    ranges overlap completely and no threshold separates them -- the 2025 Customs
    s.14A heading ("... etc PROHIBITION AND RESTRICTION OF IMPORTATION AND
    EXPORTATION") sat at 118, two under HEADING_BLEED_MIN_LEN, and a leaf that had
    lost both its subsections passed clean.  What the corrupt ones share is
    content that cannot belong to a heading: a running header, a roman folio, the
    NEXT section's row, or a chapter caption's ALL-CAPS run.
    """
    for heading in (
        "Omitted THE CUSTOMS ACT, 1969",                  # a running header
        "Omitted (viii) THE CUSTOMS ACT,1969",            # a folio, then the header
        "Omitted. 221. Savings",                          # the next section's row
        "Ministry of Defence 28. Ministry of Defence Production 29",
        "Provision of accommodation at customs ports, etc PROHIBITION AND "
        "RESTRICTION OF IMPORTATION AND EXPORTATION",     # a chapter caption
    ):
        flags = assess_section_quality(
            html_content="<p>Short body.</p>",
            plain_text="Short body.",
            section_heading=heading,
        )
        assert any(f["code"] == "heading_body_bleed" for f in flags), heading


def test_no_heading_bleed_on_legitimate_headings():
    """The real headings this must never flag -- including the corpus's longest
    clean one, which an ALL-CAPS or lowered-threshold rule would have caught."""
    for heading in (
        "Provision of accommodation at customs ports, etc",
        "Unauthorized access to or improper use of the Customs Computerized System",
        "Power to deliver certain goods with-out payment of duty and to repay "
        "duty on certain goods",
        "Digital certification from NIFT",
        "Alternative Dispute Resolution",
        "Omitted",
    ):
        flags = assess_section_quality(
            html_content="<p>Short body.</p>",
            plain_text="Short body.",
            section_heading=heading,
        )
        assert not any(f["code"] == "heading_body_bleed" for f in flags), heading


def test_parser_attaches_quality_flags_and_has_issues_status():
    html, plain = _conclusion_style_body()
    payload = {
        "metadata": {"total_pages": 10},
        "chapters": [
            {
                "code": "I",
                "heading": "Act",
                "sections": [
                    {
                        "code": "4",
                        "heading": "Conclusion",
                        "start_page": 241,
                        "end_page": 254,
                        "html": html,
                        "plain_text": plain,
                        "footnotes": [],
                    }
                ],
            }
        ],
        "schedules": [],
    }
    sections, _ = parse_json_document(
        json.dumps(payload),
        document_id="finance-2022",
    )
    assert len(sections) == 1
    codes = {flag["code"] for flag in sections[0]["quality_flags"]}
    assert {"missing_table", "footnote_glue", "wall_of_text"} <= codes
    assert sections[0]["review_status"] == "has_issues"


def test_serialize_roundtrip():
    flags = [{"code": "missing_table", "reason": "no table"}]
    raw = serialize_quality_flags(flags)
    assert deserialize_quality_flags(raw) == flags
    assert serialize_quality_flags([]) is None
    assert deserialize_quality_flags(None) == []


async def test_store_persists_quality_flags_and_elevates_pending(runtime_sandbox):
    document_id = "quality-document"
    html, plain = _conclusion_style_body()
    payload = json.loads(sample_document())
    payload["chapters"][0]["sections"][0]["html"] = html
    payload["chapters"][0]["sections"][0]["plain_text"] = plain
    payload["chapters"][0]["sections"][0]["heading"] = "Conclusion"
    sections, footnotes = parse_json_document(
        json.dumps(payload),
        document_id=document_id,
    )
    assert sections[0]["review_status"] == "has_issues"

    async with database_connection() as db:
        await db.execute(
            """
            INSERT INTO documents (
                id, name, pdf_filename, json_filename, total_sections,
                total_pages, uploaded_at, status, source_type
            ) VALUES (?, 'Act', 'a.pdf', 'a.json', 2, 3, 'now', 'pending', 'upload')
            """,
            (document_id,),
        )
        stats = await apply_parsed_document(db, document_id, sections, footnotes)
        await db.commit()
        assert stats["has_issues"] >= 1

        async with db.execute(
            "SELECT review_status, quality_flags FROM sections WHERE id = ?",
            (sections[0]["id"],),
        ) as cursor:
            row = await cursor.fetchone()
        stored = deserialize_quality_flags(row["quality_flags"])
        assert row["review_status"] == "has_issues"
        assert any(flag["code"] == "missing_table" for flag in stored)

        # Approved leaf must not be clobbered on identical re-apply.
        await db.execute(
            "UPDATE sections SET review_status = 'approved' WHERE id = ?",
            (sections[0]["id"],),
        )
        await db.commit()
        await apply_parsed_document(db, document_id, sections, footnotes)
        await db.commit()
        async with db.execute(
            "SELECT review_status FROM sections WHERE id = ?",
            (sections[0]["id"],),
        ) as cursor:
            assert (await cursor.fetchone())[0] == "approved"

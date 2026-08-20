import io

import pytest
from fastapi import UploadFile
from pypdf import PdfWriter

from backend.database import database_connection
from backend.routes.documents import replace_json, upload_document
from backend.services.corpus_lanes import (
    LANE_CUSTOMS,
    LANE_FINANCE,
    LANE_MANUAL,
    LANE_ORDINANCE,
    LANE_OTHER_ACTS,
    LANE_SALES_TAX,
    LANE_TAX_LAWS_AMENDMENT,
    classify_lane,
)
from backend.services.editions import family_key_from_name

from .conftest import active_version_id, sample_document


def test_classify_manual_upload():
    assert classify_lane("Anything", source_type="upload") == LANE_MANUAL


def test_classify_ordinance_origin_and_name():
    assert (
        classify_lane("Income Tax Ordinance 2001", source_type="acts_corpus", corpus_origin="ordinance")
        == LANE_ORDINANCE
    )
    assert (
        classify_lane(
            "Income Tax Ordinance 2001 - amended upto 30th June 2025",
            source_type="acts_corpus",
        )
        == LANE_ORDINANCE
    )


def test_classify_act_families():
    assert classify_lane("Customs Act, 1969", source_type="acts_corpus") == LANE_CUSTOMS
    assert classify_lane("The Sales Tax Act, 1990", source_type="acts_corpus") == LANE_SALES_TAX
    assert classify_lane("Finance Act, 2025", source_type="acts_corpus") == LANE_FINANCE
    assert (
        classify_lane("Finance Supplementary Act, 2022", source_type="acts_corpus")
        == LANE_FINANCE
    )
    assert (
        classify_lane("The Tax Laws (Amendment) Act, 2024", source_type="acts_corpus")
        == LANE_TAX_LAWS_AMENDMENT
    )
    assert classify_lane("FBR Act, 2007", source_type="acts_corpus") == LANE_OTHER_ACTS


def test_family_key_normalization():
    assert family_key_from_name("The Customs Act, 1969 as amended up to 30.06.2025") == (
        "customs act, 1969"
    )
    assert family_key_from_name("Customs Act ,1969 (Amended upto 30th June 2007)") == (
        "customs act, 1969"
    )
    assert family_key_from_name(
        "Income Tax Ordinance 2001 - amended upto 30th June 2025"
    ) == "income tax ordinance, 2001"
    assert family_key_from_name("Finance Act, 2025") == "finance act"


@pytest.mark.asyncio
async def test_upload_and_replace_json_carry_an_explicit_lane(runtime_sandbox):
    """``push_corpus`` re-seeds a deployment whose docs are all ``source_type=upload``.

    ``classify_lane`` can only answer ``manual`` for those, so the lane has to travel
    with the request or the Library's Source facet stays a single dead bucket.
    """
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    pdf_bytes = buffer.getvalue()

    async with database_connection() as db:

        created = await upload_document(
            pdf=UploadFile(filename="act.pdf", file=io.BytesIO(pdf_bytes)),
            json_file=UploadFile(
                filename="act.json", file=io.BytesIO(sample_document().encode())
            ),
            name="Customs Act, 1969",
            corpus_lane=LANE_CUSTOMS,
            db=db,
        )
        assert created.corpus_lane == LANE_CUSTOMS, "upload must honour the lane"

        # A garbage lane is ignored rather than stored, so the facet stays a closed set.
        bad = await upload_document(
            pdf=UploadFile(filename="b.pdf", file=io.BytesIO(pdf_bytes)),
            json_file=UploadFile(
                filename="b.json", file=io.BytesIO(sample_document().encode())
            ),
            name="Whatever Act",
            corpus_lane="not-a-lane",
            db=db,
        )
        assert bad.corpus_lane == LANE_MANUAL

        refreshed = await replace_json(
            document_id=created.id,
            json_file=UploadFile(
                filename="act.json",
                file=io.BytesIO(sample_document(second_text="Refreshed").encode()),
            ),
            note="Corpus refresh from push_corpus.",
            reviewer_name=None,
            corpus_lane=LANE_SALES_TAX,
            db=db,
            if_match=await active_version_id(db, created.id),
        )
        assert refreshed.corpus_lane == LANE_SALES_TAX, "refresh must move the lane"

        # Omitted on a later refresh: keep what is stored, never fall back to manual.
        kept = await replace_json(
            document_id=created.id,
            json_file=UploadFile(
                filename="act.json",
                file=io.BytesIO(sample_document(second_text="Again").encode()),
            ),
            note=None,
            reviewer_name=None,
            corpus_lane=None,
            if_match=await active_version_id(db, created.id),
            db=db,
        )
        assert kept.corpus_lane == LANE_SALES_TAX

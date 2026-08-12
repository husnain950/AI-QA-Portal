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

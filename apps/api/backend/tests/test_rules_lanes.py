"""Lane and family classification for the Rules corpus.

Every name here is a real filename from the Rules tree, including its quirks --
leading spaces, doubled commas, missing extensions, ALL-CAPS titles -- because those
are what ``documents.name`` will actually hold.
"""

from __future__ import annotations

import pytest

from backend.services.corpus_lanes import (
    LANE_CUSTOMS,
    LANE_CUSTOMS_RULES,
    LANE_FEDERAL_EXCISE,
    LANE_FEDERAL_EXCISE_RULES,
    LANE_INCOME_TAX_RULES,
    LANE_ORDER,
    LANE_OTHER_ACTS,
    LANE_OTHER_RULES,
    LANE_SALES_TAX,
    LANE_SALES_TAX_RULES,
    classify_lane,
    normalize_lane,
)
from backend.services.editions import family_key_from_name


def lane(name: str, origin: str = "rules") -> str:
    return classify_lane(name, source_type="acts_corpus", corpus_origin=origin)


@pytest.mark.parametrize(
    "name,expected",
    [
        (" Income Tax Rules, 2002 Amended upto 24.11.2023", LANE_INCOME_TAX_RULES),
        ("Income Tax Rules, 2002 Amended up to August, 2008", LANE_INCOME_TAX_RULES),
        ("The Sales Tax Rules, 2006 updated upto 31.10.2023", LANE_SALES_TAX_RULES),
        ("THE SALES TAX RULES, 2006 UPDATED UPTO 11.08.2014", LANE_SALES_TAX_RULES),
        # Special Procedure(s) are Sales Tax rules, not "other".
        ("Sales Tax Special Procedure (Withholding) Rules, 2007", LANE_SALES_TAX_RULES),
        ("SALES TAX SPECIAL PROCEDURES RULES,, 2007 UPDATED UPTO 05.03.2015",
         LANE_SALES_TAX_RULES),
        ("Customs Rules, 2001 (Updated Up to 30.06.2023)", LANE_CUSTOMS_RULES),
        ("Customs Reward Rules, 2012", LANE_OTHER_RULES),
        ("Federal Excise Rules, 2005 (updated upto 31-10-2023)", LANE_FEDERAL_EXCISE_RULES),
        ("Federal Excise Rule Updated Upto 10.07.2014", LANE_FEDERAL_EXCISE_RULES),
        ("AML_CFT Sanction Rules, 2020", LANE_OTHER_RULES),
        ("Benami Transactions (Prohibition) Rules, 2019", LANE_OTHER_RULES),
        ("FBR AML_CFT Regulations", LANE_OTHER_RULES),
        (" SRO 1127(I)_2012 dated 12.09.2012", LANE_OTHER_RULES),
        ("The Pakistan Single Window (Deputation_Secondment of Civil Servants) "
         "Regulations, 2021", LANE_OTHER_RULES),
    ],
)
def test_rules_lane(name, expected):
    assert lane(name) == expected


@pytest.mark.parametrize(
    "name,expected",
    [
        # The Act keeps its Act lane; only the Rules move.
        ("The Federal Excise Act, 2005 (amended up to 30th June 2023)", LANE_FEDERAL_EXCISE),
        ("Customs Act, 1969 as amended up to 30.06.2023", LANE_CUSTOMS),
        ("The Sales Tax Act, 1990", LANE_SALES_TAX),
    ],
)
def test_acts_are_not_pulled_into_a_rules_lane(name, expected):
    assert lane(name, origin="acts") == expected


def test_corpus_origin_outranks_the_title():
    """An Act filed in the Acts corpus stays an Act even when titled "Regulations"."""
    name = "Some Regulatory Framework Regulations Act, 2020"
    assert lane(name, origin="acts") == LANE_OTHER_ACTS
    assert lane(name, origin="rules") == LANE_OTHER_RULES


def test_all_new_lanes_are_registered():
    """An unregistered lane is dropped by normalize_lane and silently reclassified."""
    for value in (
        LANE_INCOME_TAX_RULES,
        LANE_SALES_TAX_RULES,
        LANE_CUSTOMS_RULES,
        LANE_FEDERAL_EXCISE_RULES,
        LANE_OTHER_RULES,
    ):
        assert value in LANE_ORDER
        assert normalize_lane(value) == value


@pytest.mark.parametrize(
    "names,expected",
    [
        (
            [
                "Sales Tax Rules 2006 (amended up to 30th June 2015)",
                "Sales Tax Rules 2006 updated upto 30-06-2025",
                "Sales Tax Rules, 2006 (Updated upto 01-01-2025)",
                "THE SALES TAX RULES, 2006 UPDATED UPTO 11.08.2014",
                "The Sales Tax Rules, 2006 updated upto 30.06.2020",
                "The Sales Tax Rules, 2006 updated upto 31.12.2020",
            ],
            "sales tax rules, 2006",
        ),
        (
            [
                " Income Tax Rules, 2002 Amended upto 24.11.2023",
                "Income Tax Rules, 2002 Amended up to August, 2008",
            ],
            "income tax rules, 2002",
        ),
        (
            [
                "Federal Excise Rule Updated Upto 10.07.2014",
                "Federal Excise Rules 2005 (amended up to 30th June 2015)",
                "Federal Excise Rules, 2005 (updated upto 31-10-2023)",
            ],
            "federal excise rules, 2005",
        ),
    ],
)
def test_editions_of_one_instrument_share_a_family(names, expected):
    assert {family_key_from_name(n) for n in names} == {expected}


def test_withholding_rules_stay_separate_from_special_procedures():
    """Different instruments. Stripping "(Withholding)" would merge them."""
    withholding = family_key_from_name(
        "Sales Tax Special Procedure (Withholding) Rules, 2007 (amended up to 30th June 2015)"
    )
    procedures = family_key_from_name(
        "Sales Tax Special Procedures Rules, 2007 (amended up to 30th June 2015)"
    )
    assert withholding != procedures


def test_updated_is_not_read_as_dated():
    """The bug this fixes: an unanchored `dated` matched inside "UP|DATED"."""
    assert family_key_from_name("Widget Rules, 2006 UPDATED UPTO 11.08.2014") == (
        "widget rules, 2006"
    )

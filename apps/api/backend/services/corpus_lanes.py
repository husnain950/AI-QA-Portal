"""Corpus lane taxonomy for Library Source facets.

Lanes are legal-corpus categories (Ordinance, Customs, …), not ingest path.
``source_type`` remains acts_corpus | upload; ``corpus_lane`` is the browse facet.
"""

from __future__ import annotations

import re
from typing import Optional

LANE_ORDINANCE = "ordinance"
LANE_CUSTOMS = "customs"
LANE_SALES_TAX = "sales_tax"
LANE_FEDERAL_EXCISE = "federal_excise"
LANE_FINANCE = "finance"
LANE_TAX_LAWS_AMENDMENT = "tax_laws_amendment"
LANE_OTHER_ACTS = "other_acts"
LANE_INCOME_TAX_RULES = "income_tax_rules"
LANE_SALES_TAX_RULES = "sales_tax_rules"
LANE_CUSTOMS_RULES = "customs_rules"
LANE_FEDERAL_EXCISE_RULES = "federal_excise_rules"
LANE_OTHER_RULES = "other_rules"
LANE_MANUAL = "manual"

LANE_ORDER = (
    LANE_ORDINANCE,
    LANE_CUSTOMS,
    LANE_SALES_TAX,
    LANE_FEDERAL_EXCISE,
    LANE_FINANCE,
    LANE_TAX_LAWS_AMENDMENT,
    LANE_OTHER_ACTS,
    LANE_INCOME_TAX_RULES,
    LANE_SALES_TAX_RULES,
    LANE_CUSTOMS_RULES,
    LANE_FEDERAL_EXCISE_RULES,
    LANE_OTHER_RULES,
    LANE_MANUAL,
)

LANE_LABELS = {
    LANE_ORDINANCE: "Income Tax Ordinance",
    LANE_CUSTOMS: "Customs",
    LANE_SALES_TAX: "Sales Tax",
    LANE_FEDERAL_EXCISE: "Federal Excise",
    LANE_FINANCE: "Finance Acts",
    LANE_TAX_LAWS_AMENDMENT: "Tax Laws Amendments",
    LANE_OTHER_ACTS: "Other Acts",
    LANE_INCOME_TAX_RULES: "Income Tax Rules",
    LANE_SALES_TAX_RULES: "Sales Tax Rules",
    LANE_CUSTOMS_RULES: "Customs Rules",
    LANE_FEDERAL_EXCISE_RULES: "Federal Excise Rules",
    LANE_OTHER_RULES: "Other Rules & Regulations",
    LANE_MANUAL: "Manual",
}

#: A statutory instrument rather than primary legislation. Whole words only: an Act
#: whose title merely contains "ruling" or "regulatory" is not a set of Rules.
_INSTRUMENT_RE = re.compile(r"\b(rules?|regulations?)\b")

_KNOWN = frozenset(LANE_ORDER)


def lane_label(lane: Optional[str]) -> str:
    if not lane:
        return "Unknown"
    return LANE_LABELS.get(lane, lane)


def classify_lane(
    name: str,
    *,
    source_type: str = "upload",
    corpus_origin: Optional[str] = None,
) -> str:
    """Return a corpus_lane id for a document.

    ``corpus_origin`` is the sync job label when known (``ordinance`` | ``acts``).
    """
    if source_type and source_type != "acts_corpus":
        return LANE_MANUAL

    if corpus_origin == "ordinance":
        return LANE_ORDINANCE

    text = re.sub(r"\s+", " ", (name or "").strip()).lower()
    if not text:
        return LANE_OTHER_ACTS if source_type == "acts_corpus" else LANE_MANUAL

    # Rules first. The Act tests below match on bare subject words ("federal excise",
    # "sales tax act"), so "Federal Excise Rules 2005" would land in the Federal Excise
    # ACTS lane -- a statutory instrument filed under the statute it was made under.
    #
    # The sync job outranks the title. A document that came from the Acts corpus stays
    # an Act even if it is called "... Regulations", because the corpus it was filed in
    # is a stronger signal than a word in a filename; the title heuristic exists for
    # uploads, which carry no origin at all.
    if corpus_origin == "rules" or (
        corpus_origin is None and _INSTRUMENT_RE.search(text)
    ):
        if "income tax rule" in text:
            return LANE_INCOME_TAX_RULES
        # "special procedure(s)" is still Sales Tax; both forms name Sales Tax rules.
        if "sales tax rule" in text or "sales tax special procedure" in text:
            return LANE_SALES_TAX_RULES
        if "customs rule" in text:
            return LANE_CUSTOMS_RULES
        if "federal excise rule" in text:
            return LANE_FEDERAL_EXCISE_RULES
        return LANE_OTHER_RULES

    if "income tax ordinance" in text:
        return LANE_ORDINANCE
    if "customs act" in text:
        return LANE_CUSTOMS
    if "sales tax act" in text:
        return LANE_SALES_TAX
    if "federal excise" in text:
        return LANE_FEDERAL_EXCISE
    if "tax laws" in text and "amendment" in text:
        return LANE_TAX_LAWS_AMENDMENT
    if "finance supplementary" in text or re.search(r"\bfinance act\b", text):
        return LANE_FINANCE

    if corpus_origin == "acts" or source_type == "acts_corpus":
        return LANE_OTHER_ACTS
    return LANE_MANUAL


def normalize_lane(raw: Optional[str]) -> Optional[str]:
    if raw is None or raw == "":
        return None
    value = str(raw).strip()
    return value if value in _KNOWN else None

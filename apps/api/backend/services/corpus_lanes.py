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
LANE_MANUAL = "manual"

LANE_ORDER = (
    LANE_ORDINANCE,
    LANE_CUSTOMS,
    LANE_SALES_TAX,
    LANE_FEDERAL_EXCISE,
    LANE_FINANCE,
    LANE_TAX_LAWS_AMENDMENT,
    LANE_OTHER_ACTS,
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
    LANE_MANUAL: "Manual",
}

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

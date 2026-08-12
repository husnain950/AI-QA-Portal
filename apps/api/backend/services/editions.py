"""Family / edition parsing from documents.name.

family_key is only a scope limiter: a wrong key can under-merge, never make
propagation unsound.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

_DATE_PATTERNS = [
    re.compile(
        r"(?:amended|upto|up\s*to|as\s+on|dated).{0,40}?"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        re.I,
    ),
    re.compile(
        r"(?:amended|upto|up\s*to|as\s+on|dated).{0,40}?\b((?:19|20)\d{2})\b",
        re.I,
    ),
    re.compile(r"\b(20\d{2}|19\d{2})\s*[-–]\s*(\d{2})\b"),
    re.compile(r"\b(20\d{2}|19\d{2})\b"),
]

# Canonical display titles for well-known statute families (after normalization).
_CANONICAL_FAMILIES = (
    (re.compile(r"^income\s+tax\s+ordinance(?:\s*,?\s*2001)?$", re.I), "income tax ordinance, 2001"),
    (re.compile(r"^customs\s+act(?:\s*,?\s*1969)?$", re.I), "customs act, 1969"),
    (re.compile(r"^sales\s+tax\s+act(?:\s*,?\s*1990)?$", re.I), "sales tax act, 1990"),
    (re.compile(r"^federal\s+excise\s+act(?:\s*,?\s*2005)?$", re.I), "federal excise act, 2005"),
)


def family_key_from_name(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return "unknown"
    base = re.sub(r"\(.*?\)", " ", raw)
    # ITO style: "… 2001 - amended upto …" — drop dash before amended/upto.
    base = re.sub(r"\s*[-–]\s*(?=(?:as\s+)?amended|upto|up\s*to|dated)", " ", base, flags=re.I)
    base = re.sub(r",?\s*(as\s+)?amended.*$", " ", base, flags=re.I)
    base = re.sub(r",?\s*upto.*$", " ", base, flags=re.I)
    base = re.sub(r",?\s*up\s*to.*$", " ", base, flags=re.I)
    base = re.sub(r",?\s*dated.*$", " ", base, flags=re.I)
    base = re.sub(r"^the\s+", " ", base, flags=re.I)
    base = re.sub(r"\s*,\s*", ", ", base)
    base = re.sub(r"\s+", " ", base).strip().rstrip(",").strip()
    base = base.lower() or "unknown"

    for pattern, canonical in _CANONICAL_FAMILIES:
        if pattern.match(base):
            return canonical
    # Finance Acts: collapse "finance act, 2025" → keep year out of family for grouping
    # by stripping trailing year when the title is Finance Act / Finance Supplementary Act.
    m = re.match(
        r"^(finance(?:\s+supplementary)?\s+act),?\s*(?:19|20)\d{2}(?:\s*[-–]\s*\d{2})?$",
        base,
        re.I,
    )
    if m:
        return m.group(1).lower()
    return base


def family_title_from_key(family_key: str) -> str:
    """Human title from a normalized family key."""
    raw = (family_key or "").strip()
    if not raw or raw == "unknown":
        return "Unknown statute"
    return raw[:1].upper() + raw[1:] if raw else "Unknown statute"


def edition_date_from_name(name: str) -> Dict[str, Any]:
    raw = name or ""
    for cre in _DATE_PATTERNS:
        m = cre.search(raw)
        if not m:
            continue
        if m.lastindex and m.lastindex >= 2 and m.group(1) and len(m.group(1)) == 4:
            year = int(m.group(1))
            return {"year": year, "sort_key": year, "label": str(year), "unknown": False}
        token = m.group(1)
        if re.match(r"^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$", token):
            parts = re.split(r"[./-]", token)
            year = int(parts[2])
            if year < 100:
                year += 2000
            return {"year": year, "sort_key": year, "label": str(year), "unknown": False}
        year = int(token)
        if 1900 <= year <= 2100:
            return {"year": year, "sort_key": year, "label": str(year), "unknown": False}
    return {"year": None, "sort_key": 9999, "label": "year unknown", "unknown": True}


def family_and_year(name: str) -> Tuple[str, Optional[int], int]:
    fk = family_key_from_name(name)
    ed = edition_date_from_name(name)
    return fk, ed["year"], int(ed["sort_key"])

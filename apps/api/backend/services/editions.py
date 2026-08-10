"""Family / edition parsing from documents.name.

family_key is only a scope limiter: a wrong key can under-merge, never make
propagation unsound.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

_DATE_PATTERNS = [
    re.compile(
        r"(?:amended|upto|up\s*to|as\s+on|dated)\s*(?:upto\s*)?"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        re.I,
    ),
    re.compile(r"\b(20\d{2}|19\d{2})\s*[-–]\s*(\d{2})\b"),
    re.compile(r"\b(20\d{2}|19\d{2})\b"),
]


def family_key_from_name(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return "unknown"
    base = re.sub(r"\(.*?\)", " ", raw)
    base = re.sub(r",?\s*(as\s+)?amended.*$", " ", base, flags=re.I)
    base = re.sub(r",?\s*upto.*$", " ", base, flags=re.I)
    base = re.sub(r",?\s*dated.*$", " ", base, flags=re.I)
    base = re.sub(r"\s+", " ", base).strip().rstrip(",").strip()
    return (base or "unknown").lower()


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

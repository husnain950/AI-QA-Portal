"""Structural parse-quality heuristics for ingested Acts-Discovery HTML.

Portal detection only — correct tables/footnotes must come from upstream
Acts-Discovery re-export, then sync_acts / JSON replace.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

# Critical flag codes (any of these elevate pending → has_issues on ingest).
CRITICAL_FLAGS = frozenset(
    {
        "missing_table",
        "footnote_glue",
        "wall_of_text",
        "heading_body_bleed",
    }
)

_TABLE_MENTION_RE = re.compile(
    r"(?:Table\s+\d+|see\s+Table)\b",
    re.IGNORECASE,
)
_HAS_TABLE_TAG_RE = re.compile(r"<table\b", re.IGNORECASE)
_FOOTNOTE_GLUE_RE = re.compile(r"[A-Za-z]{3,}\d\b")
_PROPER_CITE_RE = re.compile(
    r"<sup\b[^>]*>|class\s*=\s*[\"'][^\"']*\bcite\b",
    re.IGNORECASE,
)
_BLOCK_TAG_RE = re.compile(
    r"<(?:p|table|ul|ol|div|li|h[1-6])\b",
    re.IGNORECASE,
)
_SINGLE_HEADING_WRAP_RE = re.compile(
    r"^\s*<(h[1-6])\b[^>]*>[\s\S]*</\1>\s*$",
    re.IGNORECASE,
)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?](?:\s|$)")

WALL_OF_TEXT_MIN_LEN = 800
HEADING_BLEED_MIN_LEN = 120

#: Page furniture, or a SECOND section's start, inside a heading.
#:
#: Length alone cannot find this, and the corpus says so plainly.  Measured over
#: 7,390 acts headings: the longest CLEAN heading is 172 chars (s.82,
#: "Procedure in case of goods not cleared or warehoused or transshipped or
#: exported or removed from the port within twenty days ..."), while corrupt ones
#: start at 21 ("Omitted. 221. Savings").  The two ranges overlap completely, so
#: no threshold separates them -- lowering HEADING_BLEED_MIN_LEN would flag
#: hundreds of real headings and still miss the short corrupt ones.  What the
#: corrupt ones share is CONTENT that cannot belong to a heading:
#:
#:   "Omitted THE CUSTOMS ACT, 1969"                 a running header
#:   "Omitted (viii) THE CUSTOMS ACT,1969"           a folio, then the header
#:   "Omitted. 221. Savings"                         the NEXT section's row
#:   "Provision of accommodation ... PROHIBITION AND RESTRICTION OF ..."
#:                                                   a chapter caption (118 chars,
#:                                                   two under the old threshold)
#:
#: A run of four or more ALL-CAPS words is the chapter-caption/running-header
#: signal: real titles are set in title case, and the four-word floor keeps this
#: off legitimate capitalised fragments ("NIFT", "PART II", "FBR").
#: NO re.IGNORECASE -- it is the CASE that carries the signal.  Applied blindly it
#: makes the ALL-CAPS caption run match ordinary prose, and the longest legitimate
#: heading in the corpus ("Procedure in case of goods not cleared or warehoused or
#: transshipped ...") was flagged. Each alternative states the case it means.
_HEADING_FURNITURE_RE = re.compile(
    r"\b(?:THE\s+)?(?:CUSTOMS|SALES\s+TAX|FEDERAL\s+EXCISE|INCOME\s+TAX)"
    r"\s+(?:ACT|ORDINANCE|RULES)\b"                     # a running header, in caps
    r"|\([\s]*[ivxlcdmIVXLCDM]{1,7}[\s]*\)"             # a roman folio, either case
    r"|(?<!\A)\b\d{1,4}[A-Z]{0,3}\.\s+[A-Z]"            # a second section's row
    # a caption run: four or more consecutive ALL-CAPS words, one of them long.
    # Short function words must count as part of the run or it breaks at them --
    # "PROHIBITION AND RESTRICTION OF IMPORTATION AND EXPORTATION" splits at "OF".
    r"|(?:\b[A-Z][A-Z'-]+\b[\s,]+){3,}\b[A-Z][A-Z'-]{3,}\b")


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", _STRIP_TAGS_RE.sub(" ", html or "")).strip()


def assess_page_range(
    start_page: Optional[int],
    end_page: Optional[int],
    total_pages: Optional[int],
) -> Optional[Dict[str, str]]:
    """Flag a leaf whose declared pages cannot exist in the PDF it came from.

    Two of the eighty live corpus editions carry such leaves -- a year read as a folio
    (``start_page: 1995`` in a 291-page Act) and a section past the last page. Rejecting
    the whole edition, as the sync used to, hid every good leaf in it and told nobody
    what was wrong; flagging the leaf puts the defect where a reviewer can see it.
    """
    if total_pages is None:
        return None
    if not isinstance(start_page, int) or not isinstance(end_page, int):
        return {
            "code": "page_range_out_of_bounds",
            "reason": f"Leaf has no usable page range (got {start_page!r}-{end_page!r}).",
        }
    if start_page < 1 or end_page < start_page or end_page > total_pages:
        return {
            "code": "page_range_out_of_bounds",
            "reason": (
                f"Declared pages {start_page}-{end_page} fall outside the "
                f"document's 1-{total_pages}."
            ),
        }
    return None


def assess_section_quality(
    *,
    html_content: str = "",
    plain_text: str = "",
    section_heading: str = "",
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    total_pages: Optional[int] = None,
) -> List[Dict[str, str]]:
    """Return JSON-serializable flag objects: ``{code, reason}``."""

    html = html_content or ""
    plain = plain_text or ""
    heading = (section_heading or "").strip()
    body_text = plain.strip() or _strip_html(html)
    flags: List[Dict[str, str]] = []

    page_flag = assess_page_range(start_page, end_page, total_pages)
    if page_flag is not None:
        flags.append(page_flag)

    combined_for_table = f"{plain}\n{html}"
    if _TABLE_MENTION_RE.search(combined_for_table) and not _HAS_TABLE_TAG_RE.search(
        html
    ):
        flags.append(
            {
                "code": "missing_table",
                "reason": (
                    "Mentions a table (e.g. Table N / see Table) but HTML has no "
                    "<table>"
                ),
            }
        )

    if _FOOTNOTE_GLUE_RE.search(body_text) and not _PROPER_CITE_RE.search(html):
        flags.append(
            {
                "code": "footnote_glue",
                "reason": (
                    "Body has letter+digit glue (e.g. estimates7) without proper "
                    "<sup> / .cite markers"
                ),
            }
        )

    body_len = len(body_text)
    block_tags = _BLOCK_TAG_RE.findall(html)
    single_heading_body = bool(_SINGLE_HEADING_WRAP_RE.match(html.strip()))
    if body_len > WALL_OF_TEXT_MIN_LEN and (
        single_heading_body or len(block_tags) <= 1
    ):
        flags.append(
            {
                "code": "wall_of_text",
                "reason": (
                    f"Long body ({body_len} chars) lacks real block structure "
                    "(or is stuffed into a single heading tag)"
                ),
            }
        )

    if heading and (
        len(heading) > HEADING_BLEED_MIN_LEN
        or len(_SENTENCE_SPLIT_RE.findall(heading)) >= 2
        or _HEADING_FURNITURE_RE.search(heading)
    ):
        flags.append(
            {
                "code": "heading_body_bleed",
                "reason": (
                    "Section heading looks like body text "
                    f"({len(heading)} chars / multiple sentences / "
                    "page furniture)"
                ),
            }
        )

    return flags


def has_critical_flags(flags: Optional[Sequence[Dict[str, Any]]]) -> bool:
    if not flags:
        return False
    return any(str(flag.get("code") or "") in CRITICAL_FLAGS for flag in flags)


def serialize_quality_flags(
    flags: Optional[Sequence[Dict[str, Any]]],
) -> Optional[str]:
    if not flags:
        return None
    return json.dumps(list(flags), ensure_ascii=False)


def deserialize_quality_flags(raw: Any) -> List[Dict[str, str]]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [
            {"code": str(item.get("code", "")), "reason": str(item.get("reason", ""))}
            for item in raw
            if isinstance(item, dict)
        ]
    if not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return deserialize_quality_flags(parsed)

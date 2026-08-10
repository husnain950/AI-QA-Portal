import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.services.parse_quality import (
    assess_section_quality,
    has_critical_flags,
)


def _stable_id(document_id: Optional[str], source_key: str) -> str:
    if not document_id:
        return str(uuid.uuid4())
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"pdf-qa-portal:{document_id}:{source_key}",
        )
    )


_GAZETTE_RE = re.compile(r"THE\s+GAZETTE\s+OF\s+PAKISTAN", re.I)
_CONTENTS_MARKER_RE = re.compile(r"Section\s+Page\s+No\.?", re.I)
_DOT_LEADERS_RE = re.compile(r"(?:[.\u2026·•]{2,}|\u2026+)")
_LEADING_JUNK_RE = re.compile(r"^[\]\s|]+")
_TRAILING_TOC_PAGE_RE = re.compile(
    r"[\s.·•…]*\d{1,4}(?:\s*[-–]\s*\d{1,4})?"
    r"(?:\s+Chapter[-–]?\s*[IVXLC0-9]+)?\s*$",
    re.I,
)
_GAZETTE_PREFIX_RE = re.compile(
    r"^\]?\s*THE\s+GAZETTE\s+OF\s+PAKISTAN"
    r"(?:[\s,.]|EXTRA\.?|EXTRAORDINARY|ISLAMABAD|"
    r"MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY|"
    r"JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|"
    r"OCTOBER|NOVEMBER|DECEMBER|"
    r"\d{1,4})*",
    re.I,
)
_CONTAINER_CODE_RE = re.compile(
    r"^(PART|CHAPTER|SCHEDULE|DIVISION|PREAMBLE)\b",
    re.I,
)


def _blank_to_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_heading(heading: Any) -> str:
    """Strip TOC chrome that leaks into Act section headings."""
    text = str(heading or "").strip()
    if not text:
        return ""

    text = _LEADING_JUNK_RE.sub("", text)
    had_gazette = bool(_GAZETTE_RE.search(text))
    had_leaders = bool(_DOT_LEADERS_RE.search(text))
    had_contents = bool(_CONTENTS_MARKER_RE.search(text))

    if had_gazette:
        text = _GAZETTE_PREFIX_RE.sub("", text).strip()
    if had_leaders:
        text = _DOT_LEADERS_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Only strip trailing page nums when TOC chrome was present.
    if had_gazette or had_leaders or had_contents:
        text = _TRAILING_TOC_PAGE_RE.sub("", text).strip(" .·•…")
        text = text.rstrip(" .")
    if had_contents:
        text = _CONTENTS_MARKER_RE.sub("", text).strip()
    return text


def is_junk_leaf(sec_data: Dict[str, Any]) -> bool:
    """True for CONTENTS-page / gazette-masthead fragments mistaken as sections.

    Disposition A addressable Contents leaves (`code=Contents`, heading
    `Contents · pN`) are kept — they are the intentional TOC sink, not junk.
    """
    code = str(sec_data.get("code") or "").strip()
    heading = str(sec_data.get("heading") or "")
    plain = str(sec_data.get("plain_text") or "")
    html = str(sec_data.get("html") or "")
    combined = f"{heading}\n{plain}\n{html}"

    if code == "Contents" or heading.startswith("Contents"):
        return False

    if _CONTENTS_MARKER_RE.search(combined):
        return True

    # Short gazette masthead scraps (often with a leading "]").
    if _GAZETTE_RE.search(heading):
        body = plain.strip() or re.sub(r"<[^>]+>", " ", html)
        body = re.sub(r"\s+", " ", body).strip()
        # Body that is itself mostly the masthead (no real section text).
        body_without_gazette = _GAZETTE_PREFIX_RE.sub("", body).strip()
        if len(body_without_gazette) < 80 and (
            not code
            or _CONTAINER_CODE_RE.match(code)
            or _GAZETTE_RE.search(body)
        ):
            return True

    # Container-coded leaf whose body is a CONTENTS listing.
    #
    # Only the explicit "Page No" column header counts. There used to be a second arm
    # here — four or more lines, three of them ending in a number — and on this corpus
    # it had 226 false positives and no true positives: it swallowed the Customs Act
    # §156 offences table, whose right-hand column is a list of section references, and
    # with it up to 40,000 characters of statute per leaf. Those leaves were dropped
    # before they reached the reviewer, which is a worse failure than any mislabelling.
    # A numeric right-hand column is a table, not a table of contents.
    if _CONTAINER_CODE_RE.match(code) and "Page No" in plain:
        return True

    return False


def parse_json_document(
    json_content: str,
    document_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Flatten the enriched legal JSON into page-addressable review units.

    ``source_key`` is a stable JSON-pointer-style path. It deliberately does not
    use legal section codes because those codes repeat heavily in schedules and
    amendment Acts.
    """

    data = json.loads(json_content)
    sections: List[Dict[str, Any]] = []
    footnotes: List[Dict[str, Any]] = []
    sort_order = 0
    # The document's own page count, used to flag leaves that claim a page the PDF
    # cannot have. Flagged here rather than in any one ingest path so every caller --
    # upload, JSON replace and corpus sync -- gets the same check.
    declared_pages = (data.get("metadata") or {}).get("total_pages")
    if not isinstance(declared_pages, int) or declared_pages < 1:
        declared_pages = None

    def process_section(
        sec_data: Dict[str, Any],
        context: Dict[str, Any],
        source_key: str,
    ) -> None:
        nonlocal sort_order

        if is_junk_leaf(sec_data):
            return

        section_id = _stable_id(document_id, source_key)
        start_page = sec_data.get("start_page") or sec_data.get("page_number")
        end_page = sec_data.get("end_page") or start_page
        html_content = sec_data.get("html", "") or ""
        plain_text = sec_data.get("plain_text", "") or ""
        section_heading = normalize_heading(sec_data.get("heading"))
        quality_flags = assess_section_quality(
            html_content=html_content,
            plain_text=plain_text,
            section_heading=section_heading,
            start_page=start_page,
            end_page=end_page,
            total_pages=declared_pages,
        )
        review_status = (
            "has_issues" if has_critical_flags(quality_flags) else "pending"
        )

        sec_row = {
            "id": section_id,
            "source_key": source_key,
            "chapter_code": context.get("chapter_code"),
            "chapter_heading": context.get("chapter_heading"),
            "part_code": context.get("part_code"),
            "part_heading": context.get("part_heading"),
            "division_code": context.get("division_code"),
            "division_heading": context.get("division_heading"),
            "hierarchy_kind": context.get("hierarchy_kind"),
            "section_code": str(sec_data.get("code") or "").strip(),
            "section_heading": section_heading,
            "start_page": start_page,
            "end_page": end_page,
            "html_content": html_content,
            "plain_text": plain_text,
            "sort_order": sort_order,
            "review_status": review_status,
            "quality_flags": quality_flags,
        }
        sections.append(sec_row)
        sort_order += 1

        for index, footnote in enumerate(sec_data.get("footnotes") or []):
            if not isinstance(footnote, dict):
                continue
            footnote_key = f"{source_key}/footnotes/{index}"
            footnotes.append(
                {
                    "id": _stable_id(document_id, footnote_key),
                    "source_key": footnote_key,
                    "section_id": section_id,
                    "marker": footnote.get("marker", ""),
                    "page": footnote.get("page") or start_page,
                    "text": footnote.get("text", ""),
                    "html_content": footnote.get("html", ""),
                    "review_status": "pending",
                }
            )

    def process_container(
        node: Dict[str, Any],
        context: Dict[str, Any],
        source_key: str,
        kind: str,
        allow_content_leaf: bool,
    ) -> None:
        next_context = context.copy()
        code = _blank_to_none(node.get("code"))
        heading = _blank_to_none(normalize_heading(node.get("heading")))

        if kind == "chapter" or kind == "schedule":
            next_context.update(
                chapter_code=code,
                chapter_heading=heading,
                part_code=None,
                part_heading=None,
                division_code=None,
                division_heading=None,
                hierarchy_kind=kind,
            )
        elif kind == "part":
            next_context.update(
                part_code=code,
                part_heading=heading,
                division_code=None,
                division_heading=None,
            )
        elif kind == "division":
            next_context.update(
                division_code=code,
                division_heading=heading,
            )

        child_collections = ("sections", "parts", "divisions")
        has_children = any(node.get(key) for key in child_collections)
        if allow_content_leaf and "html" in node and not has_children:
            process_section(node, next_context, source_key)

        # Keep the portal's established reading order: direct sections first,
        # followed by parts and divisions.
        for index, section in enumerate(node.get("sections") or []):
            if isinstance(section, dict):
                process_section(
                    section,
                    next_context,
                    f"{source_key}/sections/{index}",
                )

        for index, part in enumerate(node.get("parts") or []):
            if isinstance(part, dict):
                process_container(
                    part,
                    next_context,
                    f"{source_key}/parts/{index}",
                    "part",
                    # rvw_export emits leaf-shaped parts (plain_text, no children)
                    # under chapters for gazette continuations / loose parts.
                    allow_content_leaf=True,
                )

        for index, division in enumerate(node.get("divisions") or []):
            if isinstance(division, dict):
                process_container(
                    division,
                    next_context,
                    f"{source_key}/divisions/{index}",
                    "division",
                    allow_content_leaf=True,
                )

    empty_context = {
        "chapter_code": None,
        "chapter_heading": None,
        "part_code": None,
        "part_heading": None,
        "division_code": None,
        "division_heading": None,
        "hierarchy_kind": None,
    }

    # Older exports keep cover/title text only under `preamble` (no page fields).
    # Newer exports also promote it into chapters[0].sections — avoid duplicating.
    preamble = data.get("preamble") or {}
    promoted = False
    for chapter in data.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for section in chapter.get("sections") or []:
            if not isinstance(section, dict):
                continue
            if (section.get("heading") or "") == "Preamble" or (
                (preamble.get("plain_text") or "").strip()
                and (section.get("plain_text") or "").strip()
                == (preamble.get("plain_text") or "").strip()
            ):
                promoted = True
                break
        if promoted:
            break
    if (
        not promoted
        and isinstance(preamble, dict)
        and (
            (preamble.get("plain_text") or "").strip()
            or (preamble.get("html") or "").strip()
        )
    ):
        process_section(
            {
                "code": preamble.get("code") or "",
                "heading": preamble.get("heading") or "Preamble",
                "html": preamble.get("html") or "",
                "plain_text": preamble.get("plain_text") or "",
                "start_page": preamble.get("start_page") or 1,
                "end_page": preamble.get("end_page")
                or preamble.get("start_page")
                or 1,
                "footnotes": preamble.get("footnotes") or [],
            },
            empty_context,
            "/preamble",
        )

    for index, chapter in enumerate(data.get("chapters") or []):
        if isinstance(chapter, dict):
            process_container(
                chapter,
                empty_context,
                f"/chapters/{index}",
                "chapter",
                allow_content_leaf=False,
            )

    for index, schedule in enumerate(data.get("schedules") or []):
        if isinstance(schedule, dict):
            process_container(
                schedule,
                empty_context,
                f"/schedules/{index}",
                "schedule",
                allow_content_leaf=False,
            )

    _apply_reading_order(sections)
    return sections, footnotes


def _apply_reading_order(sections: List[Dict[str, Any]]) -> None:
    """Renumber ``sort_order`` so the reader walks the document in page order.

    The export is a hierarchy of three sibling lists (``sections``, ``parts``,
    ``divisions``) and the walk above visits them in that fixed order. A statute whose
    loose sections interleave with its parts therefore cannot have its reading order
    expressed by the tree at all: the Customs Act 1969 walked to page 147 and then
    jumped back to page 8, and "Section N of X" counted backwards with it.

    Page order is the document's real order, so it is derived here rather than trusted
    from the nesting. The sort is stable, so two leaves that start on the same page keep
    the tree's order — sub-page position is not recoverable from the export.
    """
    sections.sort(key=lambda row: row.get("start_page") or 0)
    for index, row in enumerate(sections):
        row["sort_order"] = index

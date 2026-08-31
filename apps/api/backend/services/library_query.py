"""Shared filter/sort construction for the v2 Library endpoints.

The Library page is fully server-driven: every facet, sort, and the search box map
onto the SQL built here, so a paginated cursor can never disagree with the rows a
filter would have produced. The CASE expressions deliberately mirror the client
derivations in ``apps/web/src/utils`` (``documentLane``, ``healthFacet``,
``reviewFacet``, ``editionDateFromName``) — change one side, change the other.

All queries are flat (LATERAL aggregates instead of GROUP BY) so that filters,
sorting, COUNT(*), and LIMIT/OFFSET pagination compose without a grouping pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.services.corpus_lanes import LANE_ORDER

SOURCE_KINDS = ("native-digital", "scanned-ocr", "mixed-ocr")
HEALTH_FACETS = ("within_gate", "outside_gate", "unmeasured")
REVIEW_FACETS = ("complete", "in_progress", "untouched")
DOC_STATUSES = ("pending", "in_progress", "blocked", "approved")
MAX_IDS = 500

# Resolved browse lane, mirroring corpus_lanes.classify_lane for rows whose stored
# corpus_lane is missing/unknown: title heuristics apply to acts_corpus rows only,
# everything else is a manual upload. Keep in sync with corpusLanes.js.
_TITLE = "regexp_replace(lower(COALESCE(d.name, '')), '\\s+', ' ', 'g')"
_LANES = ", ".join(f"'{lane}'" for lane in LANE_ORDER)
LANE_SQL = f"""
CASE
    WHEN d.corpus_lane IN ({_LANES}) THEN d.corpus_lane
    WHEN d.source_type <> 'acts_corpus' THEN 'manual'
    WHEN {_TITLE} ~ '\\y(rules?|regulations?)\\y' THEN CASE
        WHEN {_TITLE} LIKE '%income tax rule%' THEN 'income_tax_rules'
        WHEN {_TITLE} LIKE '%sales tax rule%'
            OR {_TITLE} LIKE '%sales tax special procedure%' THEN 'sales_tax_rules'
        WHEN {_TITLE} LIKE '%customs rule%' THEN 'customs_rules'
        WHEN {_TITLE} LIKE '%federal excise rule%' THEN 'federal_excise_rules'
        ELSE 'other_rules'
    END
    WHEN {_TITLE} LIKE '%income tax ordinance%' THEN 'ordinance'
    WHEN {_TITLE} LIKE '%customs act%' THEN 'customs'
    WHEN {_TITLE} LIKE '%sales tax act%' THEN 'sales_tax'
    WHEN {_TITLE} LIKE '%federal excise%' THEN 'federal_excise'
    WHEN {_TITLE} LIKE '%tax laws%' AND {_TITLE} LIKE '%amendment%' THEN 'tax_laws_amendment'
    WHEN {_TITLE} LIKE '%finance supplementary%' OR {_TITLE} ~ '\\yfinance act\\y' THEN 'finance'
    ELSE 'other_acts'
END
"""

# OCR/source kind from the provenance JSON blob. IS JSON guards the cast so a
# malformed or missing blob degrades to NULL ("unknown") instead of failing.
KIND_SQL = "CASE WHEN d.provenance IS JSON THEN CAST(d.provenance AS jsonb) ->> 'source_kind' END"

# Mirrors healthFacet in documentTags.js.
HEALTH_SQL = """
CASE
    WHEN m.measured_at IS NULL THEN 'unmeasured'
    WHEN m.gate_ok IS TRUE THEN 'within_gate'
    WHEN m.gate_ok IS FALSE THEN 'outside_gate'
    WHEN m.invariants_total IS NOT NULL AND m.invariants_total > 0 THEN
        CASE WHEN m.invariants_passed = m.invariants_total THEN 'within_gate' ELSE 'outside_gate' END
    ELSE 'unmeasured'
END
"""

# Mirrors reviewFacet in documentTags.js.
REVIEW_SQL = """
CASE
    WHEN d.total_sections <= 0 OR stats.reviewed <= 0 THEN 'untouched'
    WHEN stats.reviewed >= d.total_sections THEN 'complete'
    ELSE 'in_progress'
END
"""

# Edition year: identity-confirmed date first, else the first 19xx/20xx token in
# the name (the common path of editionDateFromName). Never raises on odd input.
# substring() returns the FIRST capturing group, so the group must wrap the year.
YEAR_SQL = """
CAST(COALESCE(
    substring(d.edition_date FROM '^(\\d{4})'),
    substring(d.name FROM '((19|20)\\d{2})')
) AS INTEGER)
"""

# One row per document; review stats, version recency, and health arrive as plain
# columns so WHERE/ORDER BY can use them directly.
FROM_DOCUMENTS = """
FROM documents d
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE s.review_status <> 'pending') AS reviewed,
        COUNT(*) FILTER (WHERE s.review_status = 'approved') AS approved,
        COUNT(*) FILTER (WHERE s.review_status = 'has_issues') AS has_issues,
        COUNT(*) FILTER (WHERE s.review_status = 'pending') AS pending,
        (SELECT COUNT(*) FROM annotations a
         WHERE a.document_id = d.id AND a.status = 'open') AS open_annotations
    FROM sections s
    WHERE s.document_id = d.id
) stats ON TRUE
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS version_count, MAX(dv.created_at) AS last_version_at
    FROM document_versions dv
    WHERE dv.document_id = d.id
) vv ON TRUE
LEFT JOIN document_versions v ON v.document_id = d.id AND v.is_active = TRUE
LEFT JOIN version_metrics m ON m.version_id = v.id
"""

# Column list matching what _document_response reads (routes/documents.py).
PAGE_SELECT = """
SELECT
    d.id, d.name, d.pdf_filename, d.json_filename, d.total_sections,
    d.total_pages, d.uploaded_at, d.status, d.source_type, d.source_key,
    d.provenance, d.corpus_lane, d.withdrawn_at,
    stats.reviewed, stats.approved, stats.has_issues, stats.pending,
    stats.open_annotations,
    vv.version_count, vv.last_version_at,
    v.version_no AS active_version_no,
    v.id AS active_version_id,
    m.invariants_passed, m.invariants_total, m.cases_passed, m.cases_total,
    m.body_conserved, m.body_missing, m.footnote_conserved, m.footnote_missing,
    m.gate_ok, m.measured_at, m.detail_json
"""


# Provenance tag array, guarded so non-JSON / non-array shapes degrade to empty.
TAGS_SQL = """
CASE WHEN d.provenance IS JSON
        AND jsonb_typeof(CAST(d.provenance AS jsonb) -> 'tags') = 'array'
     THEN CAST(d.provenance AS jsonb) -> 'tags'
     ELSE CAST('[]' AS jsonb) END
"""


@dataclass(frozen=True)
class LibraryFilters:
    """Normalized filter state shared by the page, count, and facets queries."""

    q: str = ""
    lanes: tuple = ()
    kinds: tuple = ()
    health: tuple = ()
    review: tuple = ()
    flagged: bool = False
    annotations: bool = False
    status: str = ""
    years: tuple = ()
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    added_after: str = ""
    added_before: str = ""
    pages_min: Optional[int] = None
    pages_max: Optional[int] = None
    tags: tuple = ()
    ids: tuple = ()
    # Withdrawn documents are out of the Library by default: the pipeline no longer
    # produces them, so listing them beside current ones invites a reviewer to
    # approve a parse that has been retired. They are never deleted, so this is a
    # filter and not a fact about the row -- set it to see them.
    include_withdrawn: bool = False

    def fingerprint_parts(self) -> tuple:
        return (
            self.q, self.lanes, self.kinds, self.health, self.review,
            self.flagged, self.annotations, self.status,
            self.years, self.year_from, self.year_to,
            self.added_after, self.added_before,
            self.pages_min, self.pages_max, self.tags, self.ids,
            self.include_withdrawn,
        )


def _in_clause(values: tuple) -> str:
    return "(" + ", ".join("?" for _ in values) + ")"


def build_where(filters: LibraryFilters, exclude: Optional[str] = None):
    """WHERE clause + params. ``exclude`` drops one dimension so facet counts for
    that dimension still respect every *other* active filter."""
    clauses: list[str] = []
    params: list = []

    def skipped(name: str) -> bool:
        return exclude == name

    if filters.q and not skipped("q"):
        clauses.append("(d.name ILIKE ? OR d.pdf_filename ILIKE ?)")
        needle = f"%{filters.q}%"
        params.extend((needle, needle))
    if filters.lanes and not skipped("lane"):
        clauses.append(f"{LANE_SQL} IN {_in_clause(filters.lanes)}")
        params.extend(filters.lanes)
    if filters.kinds and not skipped("kind"):
        known = [kind for kind in filters.kinds if kind != "unknown"]
        parts = []
        if known:
            parts.append(f"{KIND_SQL} IN {_in_clause(tuple(known))}")
            params.extend(known)
        if "unknown" in filters.kinds:
            parts.append(f"{KIND_SQL} IS NULL")
        clauses.append("(" + " OR ".join(parts) + ")")
    if filters.health and not skipped("health"):
        clauses.append(f"{HEALTH_SQL} IN {_in_clause(filters.health)}")
        params.extend(filters.health)
    if filters.review and not skipped("review"):
        clauses.append(f"{REVIEW_SQL} IN {_in_clause(filters.review)}")
        params.extend(filters.review)
    if filters.flagged and not skipped("flags"):
        clauses.append("stats.has_issues > 0")
    if filters.annotations and not skipped("flags"):
        clauses.append("stats.open_annotations > 0")
    if filters.status and not skipped("status"):
        clauses.append("d.status = ?")
        params.append(filters.status)
    if not skipped("year"):
        if filters.years:
            clauses.append(f"{YEAR_SQL} IN {_in_clause(filters.years)}")
            params.extend(filters.years)
        if filters.year_from is not None:
            clauses.append(f"{YEAR_SQL} >= ?")
            params.append(filters.year_from)
        if filters.year_to is not None:
            clauses.append(f"{YEAR_SQL} <= ?")
            params.append(filters.year_to)
    if not skipped("dates"):
        if filters.added_after:
            clauses.append("LEFT(d.uploaded_at, 10) >= ?")
            params.append(filters.added_after)
        if filters.added_before:
            clauses.append("LEFT(d.uploaded_at, 10) <= ?")
            params.append(filters.added_before)
    if not skipped("pages"):
        if filters.pages_min is not None:
            clauses.append("d.total_pages >= ?")
            params.append(filters.pages_min)
        if filters.pages_max is not None:
            clauses.append("d.total_pages <= ?")
            params.append(filters.pages_max)
    if filters.tags and not skipped("tags"):
        # jsonb_exists is the function form of the ? operator — which would clash
        # with this codebase's qmark parameter style.
        clauses.append(
            "(" + " OR ".join(f"jsonb_exists({TAGS_SQL}, ?)" for _ in filters.tags) + ")"
        )
        params.extend(filters.tags)
    if filters.ids and not skipped("ids"):
        clauses.append(f"d.id IN {_in_clause(filters.ids)}")
        params.extend(filters.ids)
    # Deliberately NOT skippable by `exclude`: a facet count that includes withdrawn
    # documents would not match the page it labels.
    if not filters.include_withdrawn:
        clauses.append("d.withdrawn_at IS NULL")

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def where_needs_stat_joins(filters: LibraryFilters, exclude: Optional[str] = None) -> bool:
    """True when the WHERE clause reads stats / health / review (LATERAL joins)."""
    def skipped(name: str) -> bool:
        return exclude == name

    return bool(
        (filters.health and not skipped("health"))
        or (filters.review and not skipped("review"))
        or (filters.flagged and not skipped("flags"))
        or (filters.annotations and not skipped("flags"))
    )


def count_from(filters: LibraryFilters, exclude: Optional[str] = None) -> str:
    """FROM for COUNT(*). Unfiltered / name-only filters do not need per-document
    section scans; those LATERAL joins are what made Library time out on a
    single API worker against a real corpus."""
    return FROM_DOCUMENTS if where_needs_stat_joins(filters, exclude) else "FROM documents d"


SORTS = {
    "name": "lower(d.name), d.id",
    "name_desc": "lower(d.name) DESC, d.id",
    "newest": "d.uploaded_at DESC, d.id",
    "oldest": "d.uploaded_at, d.id",
    "updated": "vv.last_version_at DESC NULLS LAST, d.id",
    "year": f"{YEAR_SQL} DESC NULLS LAST, lower(d.name), d.id",
    "year_asc": f"{YEAR_SQL} ASC NULLS LAST, lower(d.name), d.id",
    "pages": "d.total_pages DESC, d.id",
    "pages_asc": "d.total_pages, d.id",
    "sections": "d.total_sections DESC, d.id",
    "sections_asc": "d.total_sections, d.id",
    "completion": (
        "CAST(stats.reviewed AS float) / NULLIF(d.total_sections, 0) DESC NULLS LAST, "
        "lower(d.name), d.id"
    ),
    "flagged": "stats.has_issues DESC, lower(d.name), d.id",
    "health": (
        f"CASE WHEN {HEALTH_SQL} = 'outside_gate' THEN 0 "
        f"WHEN {HEALTH_SQL} = 'within_gate' THEN 1 ELSE 2 END, lower(d.name), d.id"
    ),
    "risk": (
        "CASE d.status WHEN 'blocked' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END, "
        "lower(d.name), d.id"
    ),
}

SORT_VALUES = tuple(SORTS) + ("relevance",)


def order_sql(sort: str, q: str = ""):
    """ORDER BY clause + extra bind params (relevance needs the query text)."""
    if sort == "relevance" and q:
        return (
            "CASE WHEN d.name ILIKE (? || '%') THEN 0 ELSE 1 END, "
            "NULLIF(POSITION(lower(?) IN lower(COALESCE(d.name, ''))), 0) NULLS LAST, "
            "lower(d.name), d.id",
            (q, q),
        )
    return SORTS.get(sort, SORTS["name"]), ()

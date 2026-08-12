"""Derive document provenance tags from pipeline JSON metadata.

Mirrors the portal taxonomy used by Library facets and Review badges.
Acts pipeline may also write ``metadata.source_kind``; we still derive when
that field is missing so older corpus JSON keeps working.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import aiosqlite

from backend.models import DocumentProvenance

OCR_FULL_RATIO = 0.9

SOURCE_KIND_NATIVE = "native-digital"
SOURCE_KIND_SCANNED = "scanned-ocr"
SOURCE_KIND_MIXED = "mixed-ocr"

KNOWN_SOURCE_KINDS = frozenset(
    {SOURCE_KIND_NATIVE, SOURCE_KIND_SCANNED, SOURCE_KIND_MIXED}
)

TAG_PROVISIONAL = "ocr-provisional"
TAG_NEEDS_REVIEW = "ocr-needs-review"


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pages_ocred_list(ocr: Dict[str, Any]) -> List[int]:
    raw = ocr.get("pages_ocred")
    if not isinstance(raw, list):
        return []
    pages: List[int] = []
    for item in raw:
        page = _as_int(item)
        if page is not None and page > 0:
            pages.append(page)
    return sorted(set(pages))


def classify_source_kind(
    *,
    ocr: Optional[Dict[str, Any]],
    total_pages: Optional[int],
    explicit: Optional[str] = None,
) -> str:
    if explicit in KNOWN_SOURCE_KINDS:
        return explicit  # type: ignore[return-value]

    if not ocr:
        return SOURCE_KIND_NATIVE

    ocr_page_count = _as_int(ocr.get("pages"))
    if ocr_page_count is None:
        ocr_page_count = len(_pages_ocred_list(ocr))

    if ocr_page_count is None or ocr_page_count < 1:
        return SOURCE_KIND_NATIVE

    pages = total_pages if total_pages and total_pages > 0 else None
    if pages and (ocr_page_count / pages) >= OCR_FULL_RATIO:
        return SOURCE_KIND_SCANNED
    return SOURCE_KIND_MIXED


def derive_from_metadata(
    metadata: Optional[Dict[str, Any]],
    total_pages: Optional[int] = None,
) -> DocumentProvenance:
    """Build provenance from pipeline ``metadata`` (and optional PDF page count)."""
    meta = metadata if isinstance(metadata, dict) else {}
    pages = _as_int(total_pages)
    if pages is None:
        pages = _as_int(meta.get("total_pages"))

    ocr_raw = meta.get("ocr")
    ocr = ocr_raw if isinstance(ocr_raw, dict) else None

    explicit = meta.get("source_kind")
    if not isinstance(explicit, str):
        explicit = None

    source_kind = classify_source_kind(
        ocr=ocr,
        total_pages=pages,
        explicit=explicit,
    )

    tags: List[str] = [source_kind]
    ocr_pages: Optional[int] = None
    pages_ocred: List[int] = []
    mean_agreement: Optional[float] = None
    floor: Optional[str] = None

    if ocr:
        pages_ocred = _pages_ocred_list(ocr)
        ocr_pages = _as_int(ocr.get("pages"))
        if ocr_pages is None:
            ocr_pages = len(pages_ocred) or None

        mean_agreement = _as_float(ocr.get("mean_agreement"))
        floor_raw = ocr.get("floor")
        floor = str(floor_raw).strip() if floor_raw else None

        provisional = bool(ocr.get("provisional")) or floor == "provisional"
        if provisional:
            tags.append(TAG_PROVISIONAL)

        needs_review = _as_int(ocr.get("needs_review_tokens")) or 0
        if needs_review > 0:
            tags.append(TAG_NEEDS_REVIEW)

    # Dedupe while preserving order
    seen = set()
    unique_tags: List[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    return DocumentProvenance(
        source_kind=source_kind,
        tags=unique_tags,
        ocr_pages=ocr_pages,
        ocr_total_pages=pages,
        mean_agreement=mean_agreement,
        floor=floor,
        pages_ocred=pages_ocred,
    )


def derive_from_json_content(
    content: str | bytes,
    total_pages: Optional[int] = None,
) -> DocumentProvenance:
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    data = json.loads(content)
    metadata = data.get("metadata") if isinstance(data, dict) else None
    return derive_from_metadata(
        metadata if isinstance(metadata, dict) else {},
        total_pages=total_pages,
    )


def serialize_provenance(provenance: DocumentProvenance) -> str:
    return provenance.model_dump_json()


def deserialize_provenance(raw: Any) -> Optional[DocumentProvenance]:
    if raw is None or raw == "":
        return None
    if isinstance(raw, DocumentProvenance):
        return raw
    if isinstance(raw, dict):
        return DocumentProvenance(**raw)
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            return DocumentProvenance(**data)
    return None


def section_intersects_ocr(
    start_page: Optional[int],
    end_page: Optional[int],
    pages_ocred: List[int],
) -> bool:
    """True when any OCR'd page falls in the leaf's [start_page, end_page] range."""
    if not pages_ocred:
        return False
    start = start_page if start_page is not None else end_page
    end = end_page if end_page is not None else start_page
    if start is None or end is None:
        return False
    if end < start:
        start, end = end, start
    ocr_set = set(pages_ocred)
    return any(page in ocr_set for page in range(start, end + 1))


async def backfill_provenance_row(
    db: aiosqlite.Connection,
    *,
    document_id: str,
    json_filename: str,
    total_pages: Optional[int],
    existing_raw: Any = None,
) -> Optional[DocumentProvenance]:
    """Return stored provenance, deriving and persisting it when missing."""
    from backend.services import blob_store

    existing = deserialize_provenance(existing_raw)
    if existing is not None:
        return existing

    if not json_filename:
        return None

    path = blob_store.blob_path(json_filename)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return None

    try:
        provenance = derive_from_json_content(content, total_pages=total_pages)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None

    await db.execute(
        "UPDATE documents SET provenance = ? WHERE id = ?",
        (serialize_provenance(provenance), document_id),
    )
    return provenance

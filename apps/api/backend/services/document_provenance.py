"""Derive document provenance tags from pipeline JSON metadata.

Mirrors the portal taxonomy used by Library facets and Review badges.
Acts pipeline may also write ``metadata.source_kind``; we still derive when
that field is missing so older corpus JSON keeps working.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from backend.database import DatabaseConnection
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
TAG_PDF_INFERRED = "pdf-inferred"

# Keep aligned with the "fast enough to schedule OCR" sampling strategy in
# `tools/acts/convert_all.py`.
PDF_SAMPLE_PAGES = 8


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
    pdf_path: Optional[str] = None,
) -> DocumentProvenance:
    """Build provenance from pipeline ``metadata`` (and optional PDF page count)."""
    meta = metadata if isinstance(metadata, dict) else {}
    pages = _as_int(total_pages)
    if pages is None:
        pages = _as_int(meta.get("total_pages"))

    ocr_raw = meta.get("ocr")
    ocr_present = isinstance(ocr_raw, dict)
    ocr = ocr_raw if ocr_present else None

    explicit = meta.get("source_kind")
    if not isinstance(explicit, str):
        explicit = None

    # When JSON has no OCR block at all, fall back to a lightweight PDF scan
    # heuristic so the portal can still classify documents for facets.
    #
    # If JSON explicitly declares a known `source_kind`, treat it as ground
    # truth and never override it with PDF inference.
    if not ocr_present and pdf_path and explicit not in KNOWN_SOURCE_KINDS:
        # Import lazily so deployments that never use the fallback don't need
        # `pdfplumber` at import time.
        try:
            import pdfplumber  # type: ignore

            from acts_ingest.pagemodel import _page_is_scan
        except Exception:
            # If the dependency is missing or the PDF can't be parsed, keep the
            # safe default: native-digital.
            return DocumentProvenance(
                source_kind=SOURCE_KIND_NATIVE,
                tags=[SOURCE_KIND_NATIVE],
                ocr_pages=None,
                ocr_total_pages=pages,
                mean_agreement=None,
                floor=None,
                pages_ocred=[],
            )

        try:
            with pdfplumber.open(pdf_path) as pdf:
                n_pages = len(pdf.pages)
                if pages is None and n_pages > 0:
                    pages = n_pages
                if not n_pages:
                    return DocumentProvenance(
                        source_kind=SOURCE_KIND_NATIVE,
                        tags=[SOURCE_KIND_NATIVE],
                        ocr_pages=None,
                        ocr_total_pages=pages,
                        mean_agreement=None,
                        floor=None,
                        pages_ocred=[],
                    )

                # Sample pages evenly across the document. This is tuned for
                # scan-heavy acts: it's fast, and (empirically) misclassifies
                # a tiny fraction of truly-mixed PDFs.
                step = max(1, n_pages // PDF_SAMPLE_PAGES)
                idx = list(range(0, n_pages, step))[:PDF_SAMPLE_PAGES]
                pages_ocred = [i + 1 for i in idx if _page_is_scan(pdf.pages[i])]

                if not pages_ocred:
                    return DocumentProvenance(
                        source_kind=SOURCE_KIND_NATIVE,
                        tags=[SOURCE_KIND_NATIVE],
                        ocr_pages=None,
                        ocr_total_pages=pages,
                        mean_agreement=None,
                        floor=None,
                        pages_ocred=[],
                    )

                ratio = len(pages_ocred) / len(idx) if idx else 0.0
                source_kind = (
                    SOURCE_KIND_SCANNED if ratio >= OCR_FULL_RATIO else SOURCE_KIND_MIXED
                )

                tags = [source_kind]
                # Let reviewers distinguish "pipeline OCR provenance" from "PDF-inferred"
                # classification.
                tags.append(TAG_PDF_INFERRED)

                return DocumentProvenance(
                    source_kind=source_kind,
                    tags=tags,
                    ocr_pages=len(pages_ocred) or None,
                    ocr_total_pages=pages,
                    mean_agreement=None,
                    floor=None,
                    pages_ocred=pages_ocred,
                )
        except Exception:
            # If the PDF heuristic fails (corrupt file, pdfplumber failure, etc),
            # keep the safe default.
            return DocumentProvenance(
                source_kind=SOURCE_KIND_NATIVE,
                tags=[SOURCE_KIND_NATIVE],
                ocr_pages=None,
                ocr_total_pages=pages,
                mean_agreement=None,
                floor=None,
                pages_ocred=[],
            )

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
    pdf_path: Optional[str] = None,
) -> DocumentProvenance:
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    data = json.loads(content)
    metadata = data.get("metadata") if isinstance(data, dict) else None
    return derive_from_metadata(
        metadata if isinstance(metadata, dict) else {},
        total_pages=total_pages,
        pdf_path=pdf_path,
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
    db: DatabaseConnection,
    *,
    document_id: str,
    json_filename: str,
    total_pages: Optional[int],
    existing_raw: Any = None,
    pdf_path: Optional[str] = None,
    force_native_reinfer: bool = False,
) -> Optional[DocumentProvenance]:
    """Return stored provenance, deriving and persisting it when missing."""
    from backend.services import blob_store

    existing = deserialize_provenance(existing_raw)
    if existing is not None:
        # If the stored provenance already looks derived from OCR metadata, keep it.
        if existing.pages_ocred:
            return existing

        # If JSON includes an OCR block, it's ground truth and should win over
        # PDF heuristics.
        if json_filename:
            try:
                path = blob_store.blob_path(json_filename)
                with open(path, "r", encoding="utf-8") as handle:
                    content = handle.read()
                data = json.loads(content)
                metadata = data.get("metadata") if isinstance(data, dict) else None
                ocr_present = isinstance(metadata, dict) and isinstance(metadata.get("ocr"), dict)
                if ocr_present:
                    return existing
            except Exception:
                # If the JSON can't be parsed, don't rewrite what we already have.
                return existing

        # Only re-infer native-digital rows when explicitly requested (typically
        # by the one-time batch backfill tool).
        if not force_native_reinfer:
            return existing
        if existing.source_kind != SOURCE_KIND_NATIVE:
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
        provenance = derive_from_json_content(
            content,
            total_pages=total_pages,
            pdf_path=pdf_path,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None

    await db.execute(
        "UPDATE documents SET provenance = ? WHERE id = ?",
        (serialize_provenance(provenance), document_id),
    )
    return provenance

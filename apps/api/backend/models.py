from typing import List, Optional

from pydantic import BaseModel, ConfigDict

# --- Document Models ---

class DocumentStats(BaseModel):
    reviewed: int
    approved: int
    has_issues: int
    pending: int
    # Explicit dual metrics — never use bare "issues" for both in the UI.
    # flagged_sections mirrors has_issues (auto + reviewer section flags).
    flagged_sections: int = 0
    open_annotations: int = 0

class DocumentBase(BaseModel):
    name: str

class DocumentCreate(DocumentBase):
    pass

class DocumentResponse(DocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pdf_filename: str
    json_filename: str
    total_sections: int
    total_pages: int
    uploaded_at: str
    status: str
    source_type: str = "upload"
    source_key: Optional[str] = None
    stats: Optional[DocumentStats] = None
    version_count: int = 1
    active_version_no: int = 1
    # The pipeline's own measurements for the active parse, when they were ingested.
    health: Optional["VersionMetrics"] = None

# --- Annotation Models ---

class AnnotationBase(BaseModel):
    highlighted_text: str
    start_offset: int
    end_offset: int
    issue_description: Optional[str] = None
    severity: str = "error" # "error" | "warning" | "info"
    reviewer_name: Optional[str] = None
    footnote_id: Optional[str] = None
    status: str = "open"
    # Text either side of the highlight, captured at creation time. It is what lets an
    # annotation be re-found when a new JSON version rewrites the leaf around it.
    context_before: Optional[str] = None
    context_after: Optional[str] = None

class AnnotationCreate(AnnotationBase):
    pass

class AnnotationUpdate(BaseModel):
    issue_description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    # Reviewers clear a needs_recheck flag by confirming the finding still stands.
    anchor_status: Optional[str] = None
    disposition: Optional[str] = None

class AnnotationResponse(AnnotationBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    # NULL once the section it pointed at was dropped by a later JSON version.
    section_id: Optional[str] = None
    created_at: str
    anchor_status: str = "anchored"  # anchored | needs_recheck | orphaned
    orphan_context: Optional[dict] = None
    disposition: str = "open"

# --- Version Models ---

class VersionMetrics(BaseModel):
    invariants_passed: Optional[int] = None
    invariants_total: Optional[int] = None
    cases_passed: Optional[int] = None
    cases_total: Optional[int] = None
    body_conserved: Optional[float] = None
    body_missing: Optional[int] = None
    footnote_conserved: Optional[float] = None
    footnote_missing: Optional[int] = None
    gate_ok: Optional[bool] = None
    measured_at: Optional[str] = None
    failing_invariants: List[str] = []

class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    version_no: int
    json_filename: str
    json_sha256: str
    source_name: Optional[str] = None
    created_at: str
    created_by: Optional[str] = None
    note: Optional[str] = None
    total_sections: int = 0
    is_active: bool = False
    stats: Optional[dict] = None
    metrics: Optional[VersionMetrics] = None

# --- Footnote Models ---

class FootnoteBase(BaseModel):
    marker: str
    page: Optional[int] = None
    text: str

class FootnoteResponse(FootnoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    section_id: str
    html_content: Optional[str] = None
    review_status: str

class FootnoteStatusUpdate(BaseModel):
    review_status: str # "approved" | "has_issues" | "pending"

# --- Section Models ---

class QualityFlag(BaseModel):
    code: str
    reason: str


class SectionMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    chapter_code: Optional[str] = None
    chapter_heading: Optional[str] = None
    part_code: Optional[str] = None
    part_heading: Optional[str] = None
    division_code: Optional[str] = None
    division_heading: Optional[str] = None
    hierarchy_kind: Optional[str] = None  # "chapter" | "schedule"
    section_code: str
    section_heading: str
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    review_status: str
    annotation_count: int
    sort_order: int
    quality_flags: List[QualityFlag] = []


class SectionResponse(SectionMetadataResponse):
    html_content: Optional[str] = None
    plain_text: Optional[str] = None
    footnotes: List[FootnoteResponse] = []

class SectionStatusUpdate(BaseModel):
    review_status: str # "approved" | "has_issues" | "pending"

# --- Search Models ---

class SearchResultResponse(BaseModel):
    section_id: str
    section_code: str
    section_heading: str
    chapter_code: Optional[str] = None
    snippet: str
    match_count: int

# --- Export Models ---

class ExportSummary(BaseModel):
    total_annotations: int
    by_severity: dict
    completion_percentage: float
    generated_at: str

class SectionExport(BaseModel):
    code: str
    heading: str
    chapter: str
    pages: str
    review_status: str
    annotations: List[AnnotationBase]

class FootnoteExport(BaseModel):
    section_code: str
    marker: str
    text: str
    review_status: str

class DocumentExport(BaseModel):
    name: str
    uploaded_at: str
    total_sections: int
    reviewed: int
    approved: int
    has_issues: int

class ExportResponse(BaseModel):
    document: DocumentExport
    sections: List[SectionExport]
    footnotes: List[FootnoteExport]
    summary: ExportSummary

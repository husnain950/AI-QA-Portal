from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

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

class DocumentProvenance(BaseModel):
    """Auto-derived document tags from pipeline metadata.ocr / source_kind."""

    source_kind: str  # native-digital | scanned-ocr | mixed-ocr
    tags: List[str] = []
    ocr_pages: Optional[int] = None
    ocr_total_pages: Optional[int] = None
    mean_agreement: Optional[float] = None
    floor: Optional[str] = None  # admitted | provisional
    pages_ocred: List[int] = []


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
    provenance: Optional[DocumentProvenance] = None
    corpus_lane: Optional[str] = None


class EditionSibling(BaseModel):
    """Another edition of the same statute family (for Review switcher)."""

    id: str
    name: str
    year: Optional[int] = None
    year_label: str = "year unknown"
    corpus_lane: Optional[str] = None
    is_current: bool = False


class DocumentEditionsResponse(BaseModel):
    family_key: str
    family_title: str
    editions: List[EditionSibling] = []

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
    disposition: str = "open"
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
    reviewer_verdict: str = "pending"
    effective_status: str = "pending"
    annotation_count: int
    sort_order: int
    quality_flags: List[QualityFlag] = []


class SectionResponse(SectionMetadataResponse):
    html_content: Optional[str] = None
    plain_text: Optional[str] = None
    footnotes: List[FootnoteResponse] = []

class SectionStatusUpdate(BaseModel):
    review_status: str # compatibility name; accepted values are reviewer verdicts

# --- AI Fix Models ---

class FixProposalCreate(BaseModel):
    instructions: str
    # Must be one of the models from GET /ai-fixes/models; omitted means default.
    model_name: Optional[str] = None


class FixModelInfo(BaseModel):
    id: str
    label: str
    vision: bool = False
    input_price_per_1m: Optional[float] = None
    output_price_per_1m: Optional[float] = None


class FixModelsResponse(BaseModel):
    models: List[FixModelInfo]
    default: str


class FixValidationIssue(BaseModel):
    level: str  # "error" | "warning"
    code: str
    message: str


class FixProposalResponse(BaseModel):
    id: str
    document_id: str
    section_id: Optional[str] = None
    source_key: str
    instructions: str
    model_name: Optional[str] = None
    status: str  # "proposed" | "approved" | "rejected" | "failed"
    error: Optional[str] = None
    created_at: str
    created_by: Optional[str] = None
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    # The merged replacement leaf (pipeline JSON shape), when the model answered.
    proposed: Optional[dict] = None
    validation: List[FixValidationIssue] = []
    diff: Optional[dict] = None
    evidence: Optional[dict] = None


class FixApprovalResponse(BaseModel):
    proposal_id: str
    overlay_id: str
    version_no: int
    version_outcome: str


# --- Search Models ---

class SearchResultResponse(BaseModel):
    section_id: str
    section_code: str
    section_heading: str
    chapter_code: Optional[str] = None
    # ``snippet`` remains for the v1 frontend but is now plain text, never HTML.
    snippet: str
    snippet_text: str
    match_ranges: List[dict] = Field(default_factory=list)
    match_count: int


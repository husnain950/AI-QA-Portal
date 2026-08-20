"""PostgreSQL schema for the CRX review platform.

The production database is intentionally PostgreSQL-only.  Identifiers remain text
because they are stable UUID strings minted by the ingest layer and are already part of
exported evidence.  Legacy JSON payload columns also remain text for one compatibility
release; new operational records use JSONB.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

documents = Table(
    "documents",
    metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("pdf_filename", Text, nullable=False),
    Column("json_filename", Text, nullable=False),
    Column("total_sections", Integer, nullable=False),
    Column("total_pages", Integer, nullable=False),
    Column("uploaded_at", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("source_type", Text, nullable=False, server_default="upload"),
    Column("source_key", Text),
    Column("source_hash", Text),
    Column("provenance", Text),
    Column("corpus_lane", Text),
    Column("statute_family_id", Text),
    Column("display_title", Text),
    Column("edition_date", Text),
    Column("amendment_through_date", Text),
    Column("identity_status", Text, nullable=False, server_default="inferred"),
    Column("signoff_stage", Text, nullable=False, server_default="draft"),
    Column("signoff_reviewed_by", Text),
    Column("signoff_legal_by", Text),
    Column("row_revision", Integer, nullable=False, server_default="1"),
    CheckConstraint(
        "status IN ('pending','in_progress','blocked','approved')",
        name="ck_documents_status",
    ),
    CheckConstraint(
        "identity_status IN ('inferred','confirmed')",
        name="ck_documents_identity_status",
    ),
    CheckConstraint(
        "signoff_stage IN ('draft','reviewed','legal_approved')",
        name="ck_documents_signoff_stage",
    ),
)
Index(
    "uq_documents_source",
    documents.c.source_type,
    documents.c.source_key,
    unique=True,
    postgresql_where=documents.c.source_key.is_not(None),
)

statute_families = Table(
    "statute_families",
    metadata,
    Column("id", Text, primary_key=True),
    Column("canonical_title", Text, nullable=False),
    Column("canonical_slug", Text, nullable=False, unique=True),
    Column("aliases", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("created_at", Text, nullable=False),
    Column("confirmed_at", Text),
    Column("confirmed_by", Text),
)

document_versions = Table(
    "document_versions",
    metadata,
    Column("id", Text, primary_key=True),
    Column("document_id", Text, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("json_filename", Text, nullable=False),
    Column("json_sha256", Text, nullable=False),
    Column("source_name", Text),
    Column("created_at", Text, nullable=False),
    Column("created_by", Text),
    Column("note", Text),
    Column("total_sections", Integer, nullable=False, server_default="0"),
    Column("is_active", Boolean, nullable=False, server_default=text("false")),
    Column("stats_json", Text),
    UniqueConstraint("document_id", "version_no", name="uq_document_version_no"),
)
Index("idx_versions_document", document_versions.c.document_id, document_versions.c.version_no)
Index(
    "uq_versions_active",
    document_versions.c.document_id,
    unique=True,
    postgresql_where=document_versions.c.is_active.is_(True),
)

sections = Table(
    "sections",
    metadata,
    Column("id", Text, primary_key=True),
    Column("document_id", Text, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
    Column("chapter_code", Text),
    Column("chapter_heading", Text),
    Column("part_code", Text),
    Column("part_heading", Text),
    Column("division_code", Text),
    Column("division_heading", Text),
    Column("section_code", Text, nullable=False),
    Column("section_heading", Text, nullable=False),
    Column("start_page", Integer),
    Column("end_page", Integer),
    Column("html_content", Text),
    Column("plain_text", Text),
    Column("sort_order", Integer, nullable=False),
    Column("review_status", Text, nullable=False, server_default="pending"),
    Column("reviewer_verdict", Text, nullable=False, server_default="pending"),
    Column("effective_status", Text, nullable=False, server_default="pending"),
    Column("source_key", Text),
    Column("quality_flags", Text),
    Column("hierarchy_kind", Text),
    Column("sanitizer_version", Text),
    Column("sanitized_changed", Boolean, nullable=False, server_default=text("false")),
    Column("sanitizer_diagnostics", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("occurrence_id", Text),
    CheckConstraint("start_page IS NULL OR start_page >= 1", name="ck_sections_start_page"),
    CheckConstraint(
        "end_page IS NULL OR start_page IS NULL OR end_page >= start_page",
        name="ck_sections_page_order",
    ),
    CheckConstraint(
        "reviewer_verdict IN ('pending','approved','needs_work')",
        name="ck_sections_reviewer_verdict",
    ),
    CheckConstraint(
        "effective_status IN ('pending','blocked','approved','approved_inherited')",
        name="ck_sections_effective_status",
    ),
    CheckConstraint(
        "review_status IN ('pending','blocked','approved','approved_inherited','has_issues')",
        name="ck_sections_legacy_review_status",
    ),
)
Index("idx_sections_document", sections.c.document_id)
Index("idx_sections_pages", sections.c.document_id, sections.c.start_page, sections.c.end_page)
Index(
    "uq_sections_source",
    sections.c.document_id,
    sections.c.source_key,
    unique=True,
    postgresql_where=sections.c.source_key.is_not(None),
)

footnotes = Table(
    "footnotes",
    metadata,
    Column("id", Text, primary_key=True),
    Column("section_id", Text, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False),
    Column("marker", Text, nullable=False),
    Column("page", Integer),
    Column("text", Text, nullable=False),
    Column("html_content", Text),
    Column("review_status", Text, nullable=False, server_default="pending"),
    Column("source_key", Text),
    Column("sanitizer_version", Text),
    Column("sanitized_changed", Boolean, nullable=False, server_default=text("false")),
    Column("sanitizer_diagnostics", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    CheckConstraint(
        "review_status IN ('pending','approved','has_issues','needs_work')",
        name="ck_footnotes_review_status",
    ),
)
Index("idx_footnotes_section", footnotes.c.section_id)

annotations = Table(
    "annotations",
    metadata,
    Column("id", Text, primary_key=True),
    Column("document_id", Text, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
    Column("section_id", Text, ForeignKey("sections.id", ondelete="SET NULL")),
    Column("footnote_id", Text, ForeignKey("footnotes.id", ondelete="SET NULL")),
    Column("highlighted_text", Text, nullable=False),
    Column("context_before", Text),
    Column("context_after", Text),
    Column("start_offset", Integer, nullable=False),
    Column("end_offset", Integer, nullable=False),
    Column("issue_description", Text),
    Column("severity", Text, nullable=False, server_default="error"),
    Column("created_at", Text, nullable=False),
    Column("reviewer_name", Text),
    Column("status", Text, nullable=False, server_default="open"),
    Column("anchor_status", Text, nullable=False, server_default="anchored"),
    Column("created_version_id", Text),
    Column("orphan_context", Text),
    Column("disposition", Text, nullable=False, server_default="open"),
    CheckConstraint("start_offset >= 0 AND end_offset > start_offset", name="ck_annotations_offsets"),
    CheckConstraint("severity IN ('error','warning','info')", name="ck_annotations_severity"),
    CheckConstraint("status IN ('open','resolved')", name="ck_annotations_status"),
    CheckConstraint(
        "anchor_status IN ('anchored','needs_recheck','orphaned')",
        name="ck_annotations_anchor_status",
    ),
)
Index("idx_annotations_document", annotations.c.document_id)
Index("idx_annotations_section", annotations.c.section_id)
Index("idx_annotations_footnote", annotations.c.footnote_id)

version_metrics = Table(
    "version_metrics",
    metadata,
    Column("version_id", Text, ForeignKey("document_versions.id", ondelete="CASCADE"), primary_key=True),
    Column("invariants_passed", Integer),
    Column("invariants_total", Integer),
    Column("cases_passed", Integer),
    Column("cases_total", Integer),
    Column("body_conserved", Float),
    Column("body_missing", Integer),
    Column("footnote_conserved", Float),
    Column("footnote_missing", Integer),
    Column("gate_ok", Boolean),
    Column("measured_at", Text),
    Column("detail_json", Text),
)

corpus_sync_state = Table(
    "corpus_sync_state",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("last_sync_at", Text),
    Column("last_status", Text),
    Column("last_summary", Text),
    Column("ordinance_docs", Integer, server_default="0"),
    Column("acts_docs", Integer, server_default="0"),
    CheckConstraint("id = 1", name="ck_corpus_sync_singleton"),
)

review_events = Table(
    "review_events",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("at", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("document_id", Text),
    Column("section_id", Text),
    Column("version_id", Text),
    Column("from_value", Text),
    Column("to_value", Text),
    Column("detail_json", Text),
)

findings = Table(
    "findings",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("section_id", Text, nullable=False),
    Column("document_id", Text, nullable=False),
    Column("detector", Text, nullable=False),
    Column("detector_version", Text, nullable=False),
    Column("fingerprint", Text, nullable=False),
    Column("severity", Text, nullable=False, server_default="warning"),
    Column("score", Float),
    Column("triage", Text, nullable=False, server_default="new"),
    Column("triage_note", Text),
    Column("triaged_by", Text),
    Column("triaged_at", Text),
    Column("first_seen_at", Text, nullable=False),
    Column("last_seen_at", Text, nullable=False),
    Column("detail_json", Text),
    Column("orphaned", Boolean, nullable=False, server_default=text("false")),
    UniqueConstraint("section_id", "detector", "fingerprint", name="uq_finding_identity"),
    CheckConstraint("severity IN ('error','warning','info')", name="ck_findings_severity"),
)
Index("idx_findings_queue", findings.c.triage, findings.c.detector, findings.c.severity)
Index("idx_findings_section", findings.c.section_id)
Index("idx_findings_document", findings.c.document_id)

section_variants = Table(
    "section_variants",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("variant_key", Text, nullable=False),
    Column("section_id", Text, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False),
    Column("document_id", Text, nullable=False),
    Column("family_key", Text, nullable=False),
    Column("section_code", Text, nullable=False),
    Column("edition_date", Text),
    Column("text_sha", Text, nullable=False),
    Column("html_sha", Text, nullable=False),
    Column("html_shape", Text, nullable=False),
    Column("footnote_sha", Text),
    Column("created_at", Text, nullable=False),
    UniqueConstraint("variant_key", "section_id", name="uq_variant_section"),
)
Index("idx_variants_key", section_variants.c.variant_key)
Index("idx_variants_family", section_variants.c.family_key, section_variants.c.section_code)

approval_inheritance = Table(
    "approval_inheritance",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("source_id", Text, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False),
    Column("inheritor_id", Text, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False),
    Column("variant_key", Text, nullable=False),
    Column("inherited_at", Text, nullable=False),
    Column("policy_version", Text, nullable=False, server_default="v2"),
    Column("evidence", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    UniqueConstraint("source_id", "inheritor_id", name="uq_approval_inheritance"),
)
Index("idx_inheritance_inheritor", approval_inheritance.c.inheritor_id)
Index("idx_inheritance_source", approval_inheritance.c.source_id)

fix_proposals = Table(
    "fix_proposals",
    metadata,
    Column("id", Text, primary_key=True),
    Column("document_id", Text, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
    Column("section_id", Text, ForeignKey("sections.id", ondelete="SET NULL")),
    Column("source_key", Text, nullable=False),
    Column("original_fingerprint", Text),
    Column("instructions", Text, nullable=False),
    Column("model", Text),
    Column("proposed_json", Text),
    Column("validation_json", Text),
    Column("diff_json", Text),
    Column("status", Text, nullable=False, server_default="proposed"),
    Column("error", Text),
    Column("created_at", Text, nullable=False),
    Column("created_by", Text),
    Column("resolved_at", Text),
    Column("resolved_by", Text),
    Column("evidence_json", JSONB),
)
Index("idx_fix_proposals_document", fix_proposals.c.document_id, fix_proposals.c.created_at)

section_overlays = Table(
    "section_overlays",
    metadata,
    Column("id", Text, primary_key=True),
    Column("pdf_sha256", Text, nullable=False),
    Column("section_source_key", Text, nullable=False),
    Column("replacement_json", Text, nullable=False),
    Column("original_leaf_fingerprint", Text, nullable=False),
    Column("proposal_id", Text, ForeignKey("fix_proposals.id", ondelete="SET NULL")),
    Column("status", Text, nullable=False, server_default="active"),
    Column("created_at", Text, nullable=False),
    Column("created_by", Text),
    Column("status_changed_at", Text),
    Column("status_reason", Text),
)
Index(
    "uq_overlays_active",
    section_overlays.c.pdf_sha256,
    section_overlays.c.section_source_key,
    unique=True,
    postgresql_where=section_overlays.c.status == "active",
)
Index("idx_overlays_pdf", section_overlays.c.pdf_sha256)

jobs = Table(
    "jobs",
    metadata,
    Column("id", Text, primary_key=True),
    Column("type", Text, nullable=False),
    Column("queue", Text, nullable=False, server_default="default"),
    Column("state", Text, nullable=False, server_default="queued"),
    Column("idempotency_key", Text),
    Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("result", JSONB),
    Column("error", JSONB),
    Column("progress_current", Integer, nullable=False, server_default="0"),
    Column("progress_total", Integer),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("max_attempts", Integer, nullable=False, server_default="3"),
    Column("available_at", Text, nullable=False),
    Column("lease_owner", Text),
    Column("leased_at", Text),
    Column("heartbeat_at", Text),
    Column("cancel_requested", Boolean, nullable=False, server_default=text("false")),
    Column("actor", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("finished_at", Text),
    CheckConstraint(
        "state IN ('queued','running','succeeded','failed','cancelled')",
        name="ck_jobs_state",
    ),
    UniqueConstraint("type", "idempotency_key", name="uq_jobs_idempotency"),
)
Index("idx_jobs_claim", jobs.c.queue, jobs.c.state, jobs.c.available_at)

review_sessions = Table(
    "review_sessions",
    metadata,
    Column("id", Text, primary_key=True),
    Column("actor", Text, nullable=False),
    Column("client_session_id", Text, nullable=False),
    Column("filters", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("sort", Text, nullable=False, server_default="risk_desc"),
    Column("snapshot_at", Text, nullable=False),
    Column("current_finding_id", BigInteger),
    Column("cursor", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
)

review_assignments = Table(
    "review_assignments",
    metadata,
    Column("finding_id", BigInteger, primary_key=True),
    Column("actor", Text, nullable=False),
    Column("client_session_id", Text, nullable=False),
    Column("claimed_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
)

bulk_idempotency = Table(
    "bulk_idempotency",
    metadata,
    Column("key", Text, primary_key=True),
    Column("actor", Text, nullable=False),
    Column("request_hash", Text, nullable=False),
    Column("response", JSONB, nullable=False),
    Column("created_at", Text, nullable=False),
)

upload_staging = Table(
    "upload_staging",
    metadata,
    Column("token", Text, primary_key=True),
    Column("pdf_key", Text, nullable=False),
    Column("json_key", Text, nullable=False),
    Column("pdf_sha256", Text, nullable=False),
    Column("json_sha256", Text, nullable=False),
    Column("summary", JSONB, nullable=False),
    Column("warnings", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("created_by", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
    Column("committed_at", Text),
)

source_pages = Table(
    "source_pages",
    metadata,
    Column("id", Text, primary_key=True),
    Column("document_id", Text, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
    Column("page_number", Integer, nullable=False),
    Column("page_digest", Text),
    UniqueConstraint("document_id", "page_number", name="uq_source_page_number"),
)

leaf_occurrences = Table(
    "leaf_occurrences",
    metadata,
    Column("id", Text, primary_key=True),
    Column("document_id", Text, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
    Column("source_key", Text),
    Column("created_at", Text, nullable=False),
    Column("retired_at", Text),
)
Index(
    "uq_leaf_occurrence_source",
    leaf_occurrences.c.document_id,
    leaf_occurrences.c.source_key,
    unique=True,
    postgresql_where=leaf_occurrences.c.source_key.is_not(None),
)

leaf_revisions = Table(
    "leaf_revisions",
    metadata,
    Column("id", Text, primary_key=True),
    Column("occurrence_id", Text, ForeignKey("leaf_occurrences.id", ondelete="CASCADE"), nullable=False),
    Column("version_id", Text, ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
    Column("section_id", Text, ForeignKey("sections.id", ondelete="SET NULL")),
    Column("content_sha256", Text, nullable=False),
    Column("start_page", Integer),
    Column("end_page", Integer),
    Column("sort_order", Integer, nullable=False),
    UniqueConstraint("occurrence_id", "version_id", name="uq_leaf_revision"),
)

worker_heartbeats = Table(
    "worker_heartbeats",
    metadata,
    Column("worker_id", Text, primary_key=True),
    Column("started_at", Text, nullable=False),
    Column("heartbeat_at", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("job_id", Text),
    Column("version", Text),
)

backup_runs = Table(
    "backup_runs",
    metadata,
    Column("id", Text, primary_key=True),
    Column("kind", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("started_at", Text, nullable=False),
    Column("finished_at", Text),
    Column("manifest_sha256", Text),
    Column("detail", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
)

# Authentication. Passwords are scrypt-derived (stdlib hashlib), and a session row holds
# only the sha256 of its token, so a database read cannot resume anyone's session.
users = Table(
    "users",
    metadata,
    Column("id", Text, primary_key=True),
    Column("email", Text, nullable=False, unique=True),
    Column("display_name", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("password_salt", Text, nullable=False),
    Column("role", Text, nullable=False, server_default=text("'reader'")),
    Column("is_active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", Text, nullable=False),
    Column("last_login_at", Text),
    CheckConstraint("role IN ('reader','reviewer','admin')", name="ck_users_role"),
)

user_sessions = Table(
    "user_sessions",
    metadata,
    Column("token_sha", Text, primary_key=True),
    Column("user_id", Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
    Column("last_seen_at", Text, nullable=False),
    Column("user_agent", Text),
    Column("client_ip", Text),
)
Index("idx_user_sessions_user", user_sessions.c.user_id)

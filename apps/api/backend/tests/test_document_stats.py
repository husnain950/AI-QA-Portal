"""Upload/list document stats chrome — flagged vs reviewed vs open notes."""

from backend.models import DocumentStats
from backend.routes.documents import _document_stats


def test_document_stats_splits_flagged_and_open_annotations():
    stats = _document_stats(
        reviewed=7,
        approved=3,
        has_issues=4,
        pending=3,
        open_annotations=2,
    )
    assert isinstance(stats, DocumentStats)
    assert stats.flagged_sections == 4
    assert stats.has_issues == 4
    assert stats.open_annotations == 2
    assert stats.reviewed == 7
    assert stats.reviewed != stats.has_issues


def test_upload_stats_reviewed_is_not_copied_from_has_issues():
    """Mirrors the upload response formula after the reviewed=has_issues quirk fix."""
    sections = [
        {"review_status": "pending"},
        {"review_status": "has_issues"},
        {"review_status": "has_issues"},
        {"review_status": "approved"},
    ]
    total_sections = len(sections)
    has_issues = sum(1 for sec in sections if sec.get("review_status") == "has_issues")
    approved = sum(1 for sec in sections if sec.get("review_status") == "approved")
    pending = sum(1 for sec in sections if sec.get("review_status") == "pending")
    reviewed = total_sections - pending

    stats = _document_stats(
        reviewed=reviewed,
        approved=approved,
        has_issues=has_issues,
        pending=pending,
        open_annotations=0,
    )
    assert stats.reviewed == 3
    assert stats.has_issues == 2
    assert stats.approved == 1
    assert stats.pending == 1
    assert stats.flagged_sections == 2
    assert stats.reviewed != stats.has_issues

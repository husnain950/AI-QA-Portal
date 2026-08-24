import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from backend.database import DatabaseConnection, get_db

router = APIRouter(prefix="/documents", tags=["export"])

@router.get("/{document_id}/export")
async def export_qa_report(
    document_id: str,
    format: str = Query("json", pattern="^(json|csv)$"),
    db: DatabaseConnection = Depends(get_db)
):
    # Fetch document metadata
    async with db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)) as cursor:
        doc = await cursor.fetchone()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Fetch document stats
    query_stats = """
        SELECT 
            COUNT(CASE WHEN review_status != 'pending' THEN 1 END) as reviewed,
            COUNT(CASE WHEN review_status = 'approved' THEN 1 END) as approved,
            COUNT(CASE WHEN review_status = 'approved_inherited' THEN 1 END) as approved_inherited,
            COUNT(CASE WHEN review_status = 'has_issues' THEN 1 END) as has_issues
        FROM sections
        WHERE document_id = ?
    """
    async with db.execute(query_stats, (document_id,)) as cursor:
        stats_row = await cursor.fetchone()

    reviewed = stats_row["reviewed"]
    approved = stats_row["approved"]  # human-opened only — never inherited
    approved_inherited = stats_row["approved_inherited"]
    has_issues = stats_row["has_issues"]
    total_sections = doc["total_sections"]

    completion_percentage = round((reviewed / total_sections * 100), 2) if total_sections > 0 else 0.0

    # Fetch sections and their annotations
    sections_query = """
        SELECT id, section_code, section_heading, chapter_code, chapter_heading, start_page, end_page, review_status
        FROM sections
        WHERE document_id = ?
        ORDER BY sort_order ASC
    """
    async with db.execute(sections_query, (document_id,)) as cursor:
        sec_rows = await cursor.fetchall()

    export_sections = []
    all_annotations = []
    
    # We will build maps for footnotes and annotations
    for sec in sec_rows:
        sec_id = sec["id"]
        
        # Get annotations
        annot_query = """
            SELECT highlighted_text, start_offset, end_offset, issue_description, severity,
                   reviewer_name, created_at, disposition
            FROM annotations
            WHERE section_id = ?
            ORDER BY created_at ASC
        """
        async with db.execute(annot_query, (sec_id,)) as cursor:
            annot_rows = await cursor.fetchall()

        sec_annots = []
        source_defect_n = 0
        for a in annot_rows:
            try:
                disp = a["disposition"] or "open"
            except (KeyError, IndexError):
                disp = "open"
            if disp == "source_defect":
                source_defect_n += 1
            annot_data = {
                "highlighted_text": a["highlighted_text"],
                "start_offset": a["start_offset"],
                "end_offset": a["end_offset"],
                "issue_description": a["issue_description"],
                "severity": a["severity"],
                "reviewer_name": a["reviewer_name"],
                "created_at": a["created_at"],
                "disposition": disp,
            }
            sec_annots.append(annot_data)
            all_annotations.append({
                "section_code": sec["section_code"],
                "section_heading": sec["section_heading"],
                "chapter": f"{sec['chapter_code'] or ''} - {sec['chapter_heading'] or ''}".strip(" -"),
                "pages": f"{sec['start_page'] or ''}-{sec['end_page'] or ''}".strip("-"),
                "review_status": sec["review_status"],
                **annot_data
            })

        chapter_str = f"{sec['chapter_code'] or ''} - {sec['chapter_heading'] or ''}".strip(" -")
        pages_str = f"{sec['start_page'] or ''}-{sec['end_page'] or ''}".strip("-")
        status_label = sec["review_status"]
        if status_label == "approved" and source_defect_n:
            status_label = f"approved — {source_defect_n} known source defect{'s' if source_defect_n != 1 else ''}"
        elif status_label == "approved_inherited":
            status_label = "approved_inherited (not human-opened)"

        export_sections.append({
            "code": sec["section_code"],
            "heading": sec["section_heading"],
            "chapter": chapter_str,
            "pages": pages_str,
            "review_status": sec["review_status"],
            "review_status_label": status_label,
            "annotations": sec_annots
        })

    # Fetch footnotes
    footnotes_query = """
        SELECT s.section_code, f.marker, f.text, f.review_status
        FROM footnotes f
        JOIN sections s ON s.id = f.section_id
        WHERE s.document_id = ?
        ORDER BY s.sort_order ASC, f.marker ASC
    """
    async with db.execute(footnotes_query, (document_id,)) as cursor:
        fn_rows = await cursor.fetchall()

    export_footnotes = [{
        "section_code": f["section_code"],
        "marker": f["marker"],
        "text": f["text"],
        "review_status": f["review_status"]
    } for f in fn_rows]

    # Compute summary metrics
    total_annotations = len(all_annotations)
    by_severity = {"error": 0, "warning": 0, "info": 0}
    for a in all_annotations:
        sev = a["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if format == "json":
        return _json_response({
            "identity_assurance": "self_asserted",
            "document": {
                "name": doc["name"],
                "uploaded_at": doc["uploaded_at"],
                "total_sections": total_sections,
                "reviewed": reviewed,
                "approved": approved,
                "approved_inherited": approved_inherited,
                "has_issues": has_issues
            },
            "sections": export_sections,
            "footnotes": export_footnotes,
            "summary": {
                "total_annotations": total_annotations,
                "by_severity": by_severity,
                "completion_percentage": completion_percentage,
                "generated_at": generated_at,
                "note": "approved counts only human-opened leaves; approved_inherited is progress-only",
            },
        }, doc["name"])

    return _csv_response(all_annotations, doc["name"])


def _attachment(doc_name: str, extension: str) -> dict:
    """The Content-Disposition header for a QA report.

    The two serializers had a copy of this each, three lines apart.
    """
    clean = "".join(
        c for c in doc_name if c.isalnum() or c in (" ", "_", "-")
    ).rstrip()
    filename = f"{clean}_QA_Report.{extension}".replace(" ", "_")
    return {"Content-Disposition": f"attachment; filename={filename}"}


def _json_response(export_data: dict, doc_name: str) -> JSONResponse:
    return JSONResponse(content=export_data, headers=_attachment(doc_name, "json"))


_CSV_COLUMNS = (
    "Section Code", "Section Heading", "Chapter", "Pages", "Review Status",
    "Highlighted Text", "Issue Description", "Severity", "Reviewer", "Created At",
)


def _csv_response(annotations, doc_name: str) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_CSV_COLUMNS)
    for a in annotations:
        writer.writerow([
            a["section_code"],
            a["section_heading"],
            a["chapter"],
            a["pages"],
            a["review_status"],
            a["highlighted_text"],
            a["issue_description"] or "",
            a["severity"],
            a["reviewer_name"] or "",
            a["created_at"],
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers=_attachment(doc_name, "csv"),
    )

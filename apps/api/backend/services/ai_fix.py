"""The AI fix loop: bad leaf + PDF pages + reviewer instructions -> corrected leaf.

The model is asked for a *data* patch — a replacement leaf in the pipeline's own
JSON shape — never parser code. Its answer is merged onto the original leaf
(only whitelisted fields can change), validated, diffed, and stored as a
``fix_proposals`` row for a human to approve or reject.

Approval splices the corrected leaf into the active version JSON (becoming the
next document version through the normal ingest path, so QA carryover works the
same as any other version), and records a persistent overlay so future corpus
re-syncs keep the fix — see ``backend.services.overlays``.

Callers own the transaction: nothing here commits.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import io
import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.database import DatabaseConnection, DatabaseRow
from backend.services import blob_store, llm_client, overlays, versions
from backend.services.clock import iso_now_z as _now
from backend.services.html_sanitizer import visible_text

MAX_PAGES_SENT = 4
PROMPT_VERSION = "ai-fix-prompt-v1"
VALIDATOR_VERSION = "legal-leaf-validator-v2"
RENDER_DPI = 150
DIFF_CONTEXT_LINES = 2
MAX_DIFF_LINES = 400

# Fields the model is allowed to change on a leaf. Everything else on the
# original node (acts extras like toc_heading, ocr_review, ...) is preserved.
EDITABLE_FIELDS = ("code", "heading", "html", "plain_text", "start_page", "end_page", "footnotes")

_FORBIDDEN_HTML = re.compile(
    r"<\s*(script|style|iframe|object|embed|link|meta|form)\b"
    r"|\bon[a-z]+\s*="
    r"|javascript\s*:",
    re.IGNORECASE,
)
_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

SYSTEM_PROMPT = """\
You are a meticulous legal-document transcription fixer for a PDF-to-JSON pipeline.

You are given:
1. Images of the original PDF page(s) — the ground truth.
2. The pipeline's current JSON for one leaf section of the document.
3. A reviewer's instructions describing what the pipeline got wrong.

Produce a corrected version of the leaf as a single JSON object with exactly these keys:
- "code": the section code (string)
- "heading": the section heading (string)
- "html": the corrected body as HTML, using only simple markup (<h4>, <p>, <div>, <table>, <tr>, <td>, <th>, <sup>, <span>, <br>, <em>, <strong>, <ol>, <ul>, <li>, <blockquote>)
- "plain_text": the corrected body as plain text (must say the same thing as the html)
- "footnotes": a list of objects, each {"marker": str, "text": str, "html": str, "page": int|null, "ref": str|null}

Rules:
- Transcribe faithfully from the PDF images. Do not paraphrase, modernise spelling, or add content that is not on the page.
- Fix ONLY what the reviewer's instructions and the page images justify. Keep everything else exactly as it is in the current JSON.
- Keep the existing footnote markers and refs unless the instructions say they are wrong.
- Never include <script>, <style>, event handlers, or any active content in the html.
- Respond with ONLY the JSON object. No commentary, no markdown fences.
"""




# ---------------------------------------------------------------------------
# context gathering
# ---------------------------------------------------------------------------

def render_pdf_pages(
    pdf_path: str,
    start_page: Optional[int],
    end_page: Optional[int],
    *,
    max_pages: int = MAX_PAGES_SENT,
    dpi: int = RENDER_DPI,
) -> List[Tuple[int, bytes]]:
    """Render the leaf's 1-based page span to PNGs: ``[(page_no, png_bytes), ...]``."""
    import pypdfium2  # lazy: native library, only needed when a fix is requested

    first = int(start_page or 1)
    last = int(end_page or first)
    if last < first:
        first, last = last, first
    pages = list(range(first, last + 1))[:max_pages]

    rendered: List[Tuple[int, bytes]] = []
    doc = pypdfium2.PdfDocument(pdf_path)
    try:
        total = len(doc)
        for page_no in pages:
            if not 1 <= page_no <= total:
                continue
            image = doc[page_no - 1].render(scale=dpi / 72.0).to_pil()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            rendered.append((page_no, buffer.getvalue()))
    finally:
        doc.close()
    return rendered


def build_messages(
    leaf: Dict[str, Any],
    page_images: List[Tuple[int, bytes]],
    instructions: str,
    annotations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Chat-completions messages: system prompt + one vision user message."""
    current = {name: leaf.get(name) for name in EDITABLE_FIELDS}
    text_parts = [
        "Reviewer instructions:\n" + instructions.strip(),
    ]
    if annotations:
        notes = "\n".join(
            f'- "{row.get("highlighted_text", "")}" — '
            f'{row.get("issue_description") or "(no description)"}'
            for row in annotations
        )
        text_parts.append("Open reviewer annotations on this section:\n" + notes)
    text_parts.append(
        "Current pipeline JSON for this leaf:\n"
        + json.dumps(current, ensure_ascii=False, indent=2)
    )
    if page_images:
        pages_label = ", ".join(str(page_no) for page_no, _ in page_images)
        text_parts.append(f"The attached images are PDF page(s) {pages_label}.")
    else:
        text_parts.append(
            "No page images could be rendered; correct from the instructions and JSON only."
        )

    content: List[Dict[str, Any]] = [{"type": "text", "text": "\n\n".join(text_parts)}]
    for _page_no, png in page_images:
        encoded = base64.b64encode(png).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded}"},
            }
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def parse_model_reply(reply: str) -> Dict[str, Any]:
    """Model output -> dict. Tolerates markdown fences; raises ValueError otherwise."""
    text = _CODE_FENCE.sub("", reply.strip()).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("model reply is JSON but not an object")
    return data


# ---------------------------------------------------------------------------
# validation + diff
# ---------------------------------------------------------------------------

def merge_proposal(original: Dict[str, Any], proposal: Dict[str, Any]) -> Dict[str, Any]:
    """Original leaf with only the whitelisted fields replaced by the model's."""
    merged = dict(original)
    for name in EDITABLE_FIELDS:
        if name in proposal:
            merged[name] = proposal[name]
    return merged


def validate_leaf(
    merged: Dict[str, Any], original: Dict[str, Any]
) -> List[Dict[str, str]]:
    """Issues with the merged leaf. Any ``error`` level issue blocks approval."""
    issues: List[Dict[str, str]] = []

    def error(code: str, message: str) -> None:
        issues.append({"level": "error", "code": code, "message": message})

    def warning(code: str, message: str) -> None:
        issues.append({"level": "warning", "code": code, "message": message})

    for name in ("code", "heading", "html", "plain_text"):
        value = merged.get(name)
        if value is not None and not isinstance(value, str):
            error("bad_type", f"'{name}' must be a string")

    html = merged.get("html") or ""
    plain = merged.get("plain_text") or ""
    if isinstance(html, str) and _FORBIDDEN_HTML.search(html):
        error("unsafe_html", "html contains active content (script/style/event handlers)")
    if isinstance(plain, str) and not plain.strip() and (original.get("plain_text") or "").strip():
        error("empty_body", "plain_text became empty while the original had content")
    normalized_html_text = re.sub(r"\s+", " ", visible_text(html)).strip()
    normalized_plain = re.sub(r"\s+", " ", plain).strip()
    if normalized_html_text != normalized_plain:
        error("html_plain_parity", "HTML textContent and plain_text differ")

    original_start = original.get("start_page") or original.get("page_number")
    original_end = original.get("end_page") or original_start
    for name in ("start_page", "end_page"):
        value = merged.get(name)
        if value is None:
            continue
        if not isinstance(value, int):
            error("bad_type", f"'{name}' must be an integer")
        elif original_start and original_end and value != int(
            original_start if name == "start_page" else original_end
        ):
            error(
                "page_coverage_changed",
                f"'{name}'={value} must preserve the original span {original_start}-{original_end}",
            )

    footnotes = merged.get("footnotes")
    if footnotes is not None:
        if not isinstance(footnotes, list):
            error("bad_type", "'footnotes' must be a list")
        else:
            for index, note in enumerate(footnotes):
                if not isinstance(note, dict):
                    error("bad_type", f"footnotes[{index}] must be an object")
                    continue
                if not isinstance(note.get("marker"), str) or not isinstance(
                    note.get("text"), str
                ):
                    error(
                        "bad_footnote",
                        f"footnotes[{index}] needs string 'marker' and 'text'",
                    )
                note_html = note.get("html")
                if isinstance(note_html, str) and _FORBIDDEN_HTML.search(note_html):
                    error("unsafe_html", f"footnotes[{index}].html contains active content")
            original_markers = [str(note.get("marker")) for note in (original.get("footnotes") or [])]
            proposed_markers = [str(note.get("marker")) for note in footnotes if isinstance(note, dict)]
            if original_markers != proposed_markers:
                error("footnote_marker_conservation", "footnote marker sequence changed")

    if (
        isinstance(plain, str)
        and plain.strip() == (original.get("plain_text") or "").strip()
        and isinstance(html, str)
        and html.strip() == (original.get("html") or "").strip()
    ):
        warning("no_change", "the proposal does not change the section body")

    return issues


def has_errors(issues: List[Dict[str, str]]) -> bool:
    return any(issue["level"] == "error" for issue in issues)


def diff_leaf(original: Dict[str, Any], merged: Dict[str, Any]) -> Dict[str, Any]:
    before = original.get("plain_text") or ""
    after = merged.get("plain_text") or ""
    lines = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            lineterm="",
            n=DIFF_CONTEXT_LINES,
        )
    )[2:][:MAX_DIFF_LINES]
    return {
        "plain_text_diff": lines,
        "stats": {
            "chars_before": len(before),
            "chars_after": len(after),
            "footnotes_before": len(original.get("footnotes") or []),
            "footnotes_after": len(merged.get("footnotes") or []),
        },
    }


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

async def _document_and_section(
    db: DatabaseConnection, document_id: str, section_id: str
) -> Tuple[DatabaseRow, DatabaseRow]:
    async with db.execute(
        "SELECT * FROM documents WHERE id = ?", (document_id,)
    ) as cursor:
        document = await cursor.fetchone()
    if document is None:
        raise LookupError("document not found")
    async with db.execute(
        "SELECT * FROM sections WHERE document_id = ? AND id = ?",
        (document_id, section_id),
    ) as cursor:
        section = await cursor.fetchone()
    if section is None:
        raise LookupError("section not found")
    if not section["source_key"]:
        raise ValueError("section has no source_key; it cannot be fixed structurally")
    return document, section


async def _active_leaf(
    db: DatabaseConnection, document_id: str, source_key: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(full active JSON, leaf at source_key) for the document."""
    version = await versions.active_version(db, document_id)
    if version is None:
        raise LookupError("document has no active JSON version")
    data = json.loads(versions.read_version_json(version))
    leaf = overlays.get_leaf(data, source_key)
    if leaf is None:
        raise LookupError(f"no leaf at {source_key} in the active JSON")
    return data, leaf


async def _open_annotations(
    db: DatabaseConnection, section_id: str
) -> List[Dict[str, Any]]:
    async with db.execute(
        """
        SELECT highlighted_text, issue_description, severity
        FROM annotations
        WHERE section_id = ? AND status = 'open'
        ORDER BY created_at
        """,
        (section_id,),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def pdf_digest(db: DatabaseConnection, document) -> str:
    """The PDF's content sha256 — blob names carry it; legacy flat files are hashed."""
    digest = overlays.pdf_digest_from_filename(document["pdf_filename"])
    if digest:
        return digest
    return blob_store.sha256_file(blob_store.blob_path(document["pdf_filename"]))


async def create_proposal(
    db: DatabaseConnection,
    document_id: str,
    section_id: str,
    instructions: str,
    *,
    actor: str,
    model: str | None = None,
) -> Dict[str, Any]:
    """Ask the model for a fix and store the outcome as a ``fix_proposals`` row."""
    model = llm_client.resolve_model(model)
    document, section = await _document_and_section(db, document_id, section_id)
    source_key = section["source_key"]
    _data, leaf = await _active_leaf(db, document_id, source_key)
    original_fingerprint = overlays.leaf_fingerprint(leaf)
    annotations = await _open_annotations(db, section_id)

    pdf_path = blob_store.blob_path(document["pdf_filename"])
    try:
        page_images = render_pdf_pages(
            pdf_path, section["start_page"], section["end_page"]
        )
    except Exception:
        page_images = []  # a fix without page images is degraded, not impossible
    first_page = int(section["start_page"] or 1)
    last_page = int(section["end_page"] or first_page)
    if last_page < first_page:
        first_page, last_page = last_page, first_page
    expected_pages = list(range(first_page, last_page + 1))
    rendered_pages = [number for number, _image in page_images]
    evidence_complete = rendered_pages == expected_pages
    evidence = {
        "prompt_version": PROMPT_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "model": model,
        "source_pdf_sha256": await pdf_digest(db, document),
        "expected_pages": expected_pages,
        "rendered_pages": [
            {"page": number, "sha256": hashlib.sha256(image).hexdigest(), "bytes": len(image)}
            for number, image in page_images
        ],
        "render_result": "complete" if evidence_complete else "evidence_incomplete",
        "provider_page_limit": MAX_PAGES_SENT,
    }

    proposal_id = str(uuid.uuid4())
    row = {
        "id": proposal_id,
        "document_id": document_id,
        "section_id": section_id,
        "source_key": source_key,
        "original_fingerprint": original_fingerprint,
        "instructions": instructions,
        "model": model,
        "proposed_json": None,
        "validation_json": None,
        "diff_json": None,
        "status": "failed",
        "error": None,
        "created_at": _now(),
        "created_by": actor,
        "evidence_json": evidence,
    }

    try:
        reply = await llm_client.chat(
            build_messages(leaf, page_images, instructions, annotations),
            model=model,
        )
        proposal = parse_model_reply(reply)
        merged = merge_proposal(dict(leaf), proposal)
        issues = validate_leaf(merged, dict(leaf))
        if not evidence_complete:
            issues.append(
                {
                    "level": "error",
                    "code": "evidence_incomplete",
                    "message": "Every source page must render and fit within provider input limits",
                }
            )
        row["proposed_json"] = json.dumps(merged, ensure_ascii=False)
        row["validation_json"] = json.dumps(issues, ensure_ascii=False)
        row["diff_json"] = json.dumps(diff_leaf(dict(leaf), merged), ensure_ascii=False)
        row["status"] = (
            "evidence_incomplete"
            if not evidence_complete
            else "failed"
            if has_errors(issues)
            else "proposed"
        )
        if has_errors(issues):
            row["error"] = "; ".join(
                issue["message"] for issue in issues if issue["level"] == "error"
            )
    except (llm_client.LLMError, ValueError) as error:
        row["error"] = str(error)

    await db.execute(
        """
        INSERT INTO fix_proposals (
            id, document_id, section_id, source_key, original_fingerprint,
            instructions, model, proposed_json, validation_json, diff_json,
            status, error, created_at, created_by, evidence_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb))
        """,
        (
            row["id"],
            row["document_id"],
            row["section_id"],
            row["source_key"],
            row["original_fingerprint"],
            row["instructions"],
            row["model"],
            row["proposed_json"],
            row["validation_json"],
            row["diff_json"],
            row["status"],
            row["error"],
            row["created_at"],
            row["created_by"],
            json.dumps(row["evidence_json"], ensure_ascii=False),
        ),
    )
    return row


async def approve_proposal(
    db: DatabaseConnection, proposal, *, actor: str
) -> Dict[str, Any]:
    """Apply a proposal as a new pending version; legal approval is separate."""
    if proposal["status"] != "proposed":
        raise ValueError(f"proposal is {proposal['status']}, not open for approval")

    document_id = proposal["document_id"]
    source_key = proposal["source_key"]
    async with db.execute(
        "SELECT * FROM documents WHERE id = ?", (document_id,)
    ) as cursor:
        document = await cursor.fetchone()
    if document is None:
        raise LookupError("document not found")

    data, current_leaf = await _active_leaf(db, document_id, source_key)
    if overlays.leaf_fingerprint(current_leaf) != proposal["original_fingerprint"]:
        raise ValueError(
            "the section changed since this proposal was made; request a new fix"
        )

    merged = json.loads(proposal["proposed_json"])
    if not overlays.set_leaf(data, source_key, merged):
        raise LookupError(f"no leaf at {source_key} in the active JSON")

    digest = await pdf_digest(db, document)
    overlay_id = await overlays.upsert_overlay(
        db,
        pdf_sha256=digest,
        section_source_key=source_key,
        replacement=merged,
        original_fingerprint=proposal["original_fingerprint"],
        proposal_id=proposal["id"],
        created_by=actor,
    )

    json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    version_row, outcome = await versions.create_version(
        db,
        document_id,
        json_bytes,
        source_name=f"ai-fix-{proposal['id'][:8]}.json",
        note=f"AI fix for {source_key}, approved by {actor}",
        created_by=actor,
    )

    await db.execute(
        """
        UPDATE fix_proposals
        SET status = 'applied', resolved_at = ?, resolved_by = ?
        WHERE id = ?
        """,
        (_now(), actor, proposal["id"]),
    )
    return {
        "proposal_id": proposal["id"],
        "overlay_id": overlay_id,
        "version_no": version_row["version_no"],
        "version_outcome": outcome["status"],
        "review_status": "pending",
    }


async def reject_proposal(db: DatabaseConnection, proposal, *, actor: str) -> None:
    if proposal["status"] not in ("proposed", "failed"):
        raise ValueError(f"proposal is {proposal['status']}, not open for rejection")
    await db.execute(
        """
        UPDATE fix_proposals
        SET status = 'rejected', resolved_at = ?, resolved_by = ?
        WHERE id = ?
        """,
        (_now(), actor, proposal["id"]),
    )

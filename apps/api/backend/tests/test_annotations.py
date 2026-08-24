"""Create-annotation offset contract: HTML textContent, not plain_text."""

from types import SimpleNamespace

from backend.database import LOCK_TIMEOUT_SQLSTATE, is_lock_timeout
from backend.services import anchoring
from backend.tests.conftest import seed_document

DOCUMENT_ID = "doc-ann"
SECTION_ID = "sec-ann"

# Cite superscripts are in HTML textContent ("2.4") but only the raw marker is in
# plain_text ("4"), so the same phrase sits at different offsets in each string.
CITE_HTML = '<p>includes<sup class="cite">2.4</sup> any other officers</p>'
CITE_PLAIN = "includes 4 any other officers"
PHRASE = "any other officers"


def _offsets(text: str, phrase: str = PHRASE) -> tuple[int, int]:
    start = text.index(phrase)
    return start, start + len(phrase)


async def _section_with_cite(db):
    await seed_document(db, DOCUMENT_ID, section_ids=(SECTION_ID,), text="placeholder")
    await db.execute(
        "UPDATE sections SET html_content = ?, plain_text = ? WHERE id = ?",
        (CITE_HTML, CITE_PLAIN, SECTION_ID),
    )
    await db.commit()


def test_cite_html_and_plain_text_diverge_at_the_phrase():
    rendered = anchoring.container_text(CITE_HTML)
    html_start, _ = _offsets(rendered)
    plain_start, _ = _offsets(CITE_PLAIN)
    assert html_start != plain_start
    assert rendered[html_start:html_start + len(PHRASE)] == PHRASE
    assert CITE_PLAIN[plain_start:plain_start + len(PHRASE)] == PHRASE


async def test_create_accepts_offsets_into_rendered_html(db, client):
    await _section_with_cite(db)
    rendered = anchoring.container_text(CITE_HTML)
    start, end = _offsets(rendered)

    response = await client.post(
        f"/api/sections/{SECTION_ID}/annotations",
        json={
            "highlighted_text": PHRASE,
            "start_offset": start,
            "end_offset": end,
            "issue_description": "spacing",
            "severity": "error",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["highlighted_text"] == PHRASE
    assert body["start_offset"] == start
    assert body["anchor_status"] == "anchored"


async def test_create_rejects_offsets_that_only_fit_plain_text(db, client):
    await _section_with_cite(db)
    start, end = _offsets(CITE_PLAIN)

    response = await client.post(
        f"/api/sections/{SECTION_ID}/annotations",
        json={
            "highlighted_text": PHRASE,
            "start_offset": start,
            "end_offset": end,
            "issue_description": "spacing",
            "severity": "error",
        },
    )
    assert response.status_code == 400, response.text
    assert "does not match rendered text" in response.json()["detail"]


async def test_create_falls_back_to_plain_text_when_html_is_empty(db, client):
    await seed_document(db, DOCUMENT_ID, section_ids=(SECTION_ID,), text=CITE_PLAIN)
    await db.execute(
        "UPDATE sections SET html_content = '' WHERE id = ?",
        (SECTION_ID,),
    )
    await db.commit()
    start, end = _offsets(CITE_PLAIN)

    response = await client.post(
        f"/api/sections/{SECTION_ID}/annotations",
        json={
            "highlighted_text": PHRASE,
            "start_offset": start,
            "end_offset": end,
            "issue_description": "no html",
            "severity": "info",
        },
    )
    assert response.status_code == 200, response.text


def test_lock_timeout_sqlstate_is_detected_through_wrappers():
    inner = SimpleNamespace(sqlstate=LOCK_TIMEOUT_SQLSTATE)
    wrapped = Exception("statement timed out")
    wrapped.orig = inner  # type: ignore[attr-defined]
    assert is_lock_timeout(wrapped)
    assert not is_lock_timeout(RuntimeError("unrelated"))

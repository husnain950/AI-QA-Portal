"""The AI fix loop: proposal validation, approval, and overlay survival across syncs."""

import json

import aiosqlite
import pytest

from backend.services import ai_fix, llm_client, overlays
from backend.sync_acts import run_sync
from backend.tests.conftest import sample_document, write_pair

FIXED_TEXT = "Second section, corrected by the model"
FIXED_HTML = f"<p>{FIXED_TEXT}</p>"

# The leaf the conftest sample marks as "Repeated code" on page 3.
LEAF_KEY = "/chapters/0/sections/1"


def model_reply(**overrides) -> str:
    """A well-formed model answer for the second sample leaf."""
    payload = {
        "code": "1",
        "heading": "Repeated code",
        "html": FIXED_HTML,
        "plain_text": FIXED_TEXT,
        "footnotes": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


@pytest.fixture
def gateway(monkeypatch):
    """Configure the env and stub the network call; tests set the canned reply."""
    monkeypatch.setenv("OPENPATHS_API_KEY", "op-test")
    monkeypatch.setenv("OPENPATHS_BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("OPENPATHS_MODELS", "test-model, second-model")
    monkeypatch.delenv("OPENPATHS_MODEL", raising=False)
    monkeypatch.delenv("LLM_EXTRA_PROVIDERS", raising=False)

    state = {"reply": model_reply(), "calls": [], "models": []}

    async def fake_chat(messages, *, model=None, temperature=0.0):
        state["calls"].append(messages)
        state["models"].append(model)
        if isinstance(state["reply"], Exception):
            raise state["reply"]
        return state["reply"]

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    return state


async def synced_document(runtime_sandbox):
    source = runtime_sandbox["root"] / "export"
    write_pair(source)
    await run_sync(source)
    db = await aiosqlite.connect(runtime_sandbox["db_path"])
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON;")
    async with db.execute("SELECT id FROM documents LIMIT 1") as cursor:
        document_id = (await cursor.fetchone())["id"]
    async with db.execute(
        "SELECT id FROM sections WHERE source_key = ?", (LEAF_KEY,)
    ) as cursor:
        section_id = (await cursor.fetchone())["id"]
    return db, document_id, section_id


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------

def test_leaf_navigation_roundtrip():
    data = json.loads(sample_document())
    leaf = overlays.get_leaf(data, LEAF_KEY)
    assert leaf["heading"] == "Repeated code"

    replacement = {**leaf, "plain_text": "changed"}
    assert overlays.set_leaf(data, LEAF_KEY, replacement)
    assert overlays.get_leaf(data, LEAF_KEY)["plain_text"] == "changed"

    assert overlays.get_leaf(data, "/chapters/9/sections/0") is None
    assert not overlays.set_leaf(data, "/chapters/9/sections/0", replacement)
    assert overlays.get_leaf(data, "/not-a-key") is None


def test_leaf_fingerprint_is_order_independent():
    a = {"x": 1, "y": [1, 2]}
    b = {"y": [1, 2], "x": 1}
    assert overlays.leaf_fingerprint(a) == overlays.leaf_fingerprint(b)
    assert overlays.leaf_fingerprint(a) != overlays.leaf_fingerprint({"x": 2, "y": [1, 2]})


def test_validate_leaf_blocks_bad_proposals():
    original = json.loads(sample_document())["chapters"][0]["sections"][1]

    unsafe = ai_fix.merge_proposal(original, {"html": "<script>alert(1)</script>"})
    assert any(
        issue["code"] == "unsafe_html"
        for issue in ai_fix.validate_leaf(unsafe, original)
    )

    emptied = ai_fix.merge_proposal(original, {"plain_text": "   "})
    assert any(
        issue["code"] == "empty_body"
        for issue in ai_fix.validate_leaf(emptied, original)
    )

    drifted = ai_fix.merge_proposal(original, {"start_page": 99})
    assert any(
        issue["code"] == "page_drift"
        for issue in ai_fix.validate_leaf(drifted, original)
    )

    unchanged = ai_fix.merge_proposal(original, {})
    issues = ai_fix.validate_leaf(unchanged, original)
    assert not ai_fix.has_errors(issues)
    assert any(issue["code"] == "no_change" for issue in issues)


def test_parse_model_reply_tolerates_fences():
    assert ai_fix.parse_model_reply('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        ai_fix.parse_model_reply("[1, 2]")


def test_model_allow_list(gateway):
    assert llm_client.available_models() == ["test-model", "second-model"]
    assert llm_client.default_model() == "test-model"
    assert llm_client.resolve_model(None) == "test-model"
    assert llm_client.resolve_model("second-model") == "second-model"
    with pytest.raises(ValueError, match="unknown model"):
        llm_client.resolve_model("made-up-model")


def test_legacy_single_model_env_still_works(monkeypatch):
    monkeypatch.setenv("OPENPATHS_API_KEY", "op-test")
    monkeypatch.setenv("OPENPATHS_BASE_URL", "https://gateway.test/v1")
    monkeypatch.delenv("OPENPATHS_MODELS", raising=False)
    monkeypatch.delenv("LLM_EXTRA_PROVIDERS", raising=False)
    monkeypatch.setenv("OPENPATHS_MODEL", "only-model")
    assert llm_client.available_models() == ["only-model"]
    assert llm_client.configured()


def test_extra_providers_join_the_dropdown(gateway, monkeypatch):
    monkeypatch.setenv(
        "LLM_EXTRA_PROVIDERS",
        json.dumps(
            {
                "kimi": {
                    "base_url": "https://inference.test.modal.direct/v1",
                    "model": "user--ep-kimi-k3-server.modal.direct",
                    "env_key": "wk-test-key",
                    "extra": {"reasoning_effort": "low"},
                }
            }
        ),
    )
    # Gateway models keep dropdown order; the extra provider is appended.
    assert llm_client.available_models() == ["test-model", "second-model", "kimi"]
    assert llm_client.default_model() == "test-model"

    # The dropdown id maps onto the provider's own endpoint, key and payload.
    url, api_key, payload = llm_client.request_spec("kimi")
    assert url == "https://inference.test.modal.direct/v1/chat/completions"
    assert api_key == "wk-test-key"
    assert payload == {
        "model": "user--ep-kimi-k3-server.modal.direct",
        "reasoning_effort": "low",
    }

    # OpenPaths models are untouched by the extra registry.
    url, api_key, payload = llm_client.request_spec("second-model")
    assert url == "https://gateway.test/v1/chat/completions"
    assert api_key == "op-test"
    assert payload == {"model": "second-model"}


def test_extra_providers_alone_are_enough(monkeypatch):
    for name in ("OPENPATHS_API_KEY", "OPENPATHS_BASE_URL", "OPENPATHS_MODELS", "OPENPATHS_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "LLM_EXTRA_PROVIDERS",
        '{"kimi": {"base_url": "https://host/v1", "env_key": "wk-x"}}',
    )
    assert llm_client.configured()
    assert llm_client.available_models() == ["kimi"]
    # model falls back to the dropdown id when the spec names none
    _url, _key, payload = llm_client.request_spec(None)
    assert payload == {"model": "kimi"}


def test_broken_extra_providers_json_disables_the_feature(gateway, monkeypatch):
    monkeypatch.setenv("LLM_EXTRA_PROVIDERS", "{not json")
    assert not llm_client.configured()
    with pytest.raises(llm_client.LLMNotConfigured, match="not valid JSON"):
        llm_client.available_models()


# ---------------------------------------------------------------------------
# proposal lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_proposal_happy_path(runtime_sandbox, gateway):
    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        row = await ai_fix.create_proposal(
            db, document_id, section_id, "The body text is garbled.", actor="tester"
        )
        await db.commit()

        assert row["status"] == "proposed"
        assert row["model"] == "test-model"  # default = first configured model
        merged = json.loads(row["proposed_json"])
        assert merged["plain_text"] == FIXED_TEXT
        assert merged["start_page"] == 3  # untouched original field survives the merge
        diff = json.loads(row["diff_json"])
        assert any(line.startswith("+") for line in diff["plain_text_diff"])
        assert gateway["calls"], "the model was consulted"
        assert gateway["models"] == ["test-model"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_proposal_uses_the_requested_dropdown_model(runtime_sandbox, gateway):
    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        row = await ai_fix.create_proposal(
            db, document_id, section_id, "fix it", actor="tester",
            model="second-model",
        )
        assert row["model"] == "second-model"
        assert gateway["models"] == ["second-model"]

        with pytest.raises(ValueError, match="unknown model"):
            await ai_fix.create_proposal(
                db, document_id, section_id, "fix it", actor="tester",
                model="made-up-model",
            )
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_unsafe_reply_is_stored_as_failed(runtime_sandbox, gateway):
    gateway["reply"] = model_reply(html="<script>alert(1)</script>")
    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        row = await ai_fix.create_proposal(
            db, document_id, section_id, "fix it", actor="tester"
        )
        assert row["status"] == "failed"
        assert "active content" in row["error"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_gateway_error_is_stored_as_failed(runtime_sandbox, gateway):
    gateway["reply"] = llm_client.LLMError("gateway returned HTTP 500: boom")
    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        row = await ai_fix.create_proposal(
            db, document_id, section_id, "fix it", actor="tester"
        )
        assert row["status"] == "failed"
        assert "500" in row["error"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_approve_creates_version_overlay_and_approval(runtime_sandbox, gateway):
    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        proposal = await ai_fix.create_proposal(
            db, document_id, section_id, "fix it", actor="tester"
        )
        async with db.execute(
            "SELECT * FROM fix_proposals WHERE id = ?", (proposal["id"],)
        ) as cursor:
            stored = await cursor.fetchone()
        result = await ai_fix.approve_proposal(db, stored, actor="approver")
        await db.commit()

        assert result["version_no"] == 2
        async with db.execute(
            "SELECT plain_text, review_status FROM sections WHERE id = ?",
            (section_id,),
        ) as cursor:
            section = await cursor.fetchone()
        assert section["plain_text"] == FIXED_TEXT
        assert section["review_status"] == "approved"

        async with db.execute("SELECT * FROM section_overlays") as cursor:
            overlay_rows = [dict(row) for row in await cursor.fetchall()]
        assert len(overlay_rows) == 1
        assert overlay_rows[0]["status"] == "active"
        assert overlay_rows[0]["section_source_key"] == LEAF_KEY

        async with db.execute(
            "SELECT status FROM fix_proposals WHERE id = ?", (proposal["id"],)
        ) as cursor:
            assert (await cursor.fetchone())["status"] == "approved"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_approve_refuses_when_leaf_changed_since_proposal(
    runtime_sandbox, gateway
):
    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        proposal = await ai_fix.create_proposal(
            db, document_id, section_id, "fix it", actor="tester"
        )
        # Someone pushes a different parse before the approval happens.
        from backend.services import versions

        payload = json.loads(sample_document(second_text="Changed underneath"))
        await versions.create_version(
            db, document_id, json.dumps(payload).encode(), created_by="someone-else"
        )

        async with db.execute(
            "SELECT * FROM fix_proposals WHERE id = ?", (proposal["id"],)
        ) as cursor:
            stored = await cursor.fetchone()
        with pytest.raises(ValueError, match="changed since"):
            await ai_fix.approve_proposal(db, stored, actor="approver")
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_reject_closes_the_proposal(runtime_sandbox, gateway):
    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        proposal = await ai_fix.create_proposal(
            db, document_id, section_id, "fix it", actor="tester"
        )
        async with db.execute(
            "SELECT * FROM fix_proposals WHERE id = ?", (proposal["id"],)
        ) as cursor:
            stored = await cursor.fetchone()
        await ai_fix.reject_proposal(db, stored, actor="tester")
        await db.commit()

        async with db.execute(
            "SELECT status, resolved_by FROM fix_proposals WHERE id = ?",
            (proposal["id"],),
        ) as cursor:
            row = await cursor.fetchone()
        assert row["status"] == "rejected"
        assert row["resolved_by"] == "tester"

        with pytest.raises(ValueError):
            await ai_fix.approve_proposal(
                db,
                await (
                    await db.execute(
                        "SELECT * FROM fix_proposals WHERE id = ?", (proposal["id"],)
                    )
                ).fetchone(),
                actor="tester",
            )
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# overlays across syncs
# ---------------------------------------------------------------------------

async def _approve_fix(db, document_id, section_id):
    proposal = await ai_fix.create_proposal(
        db, document_id, section_id, "fix it", actor="tester"
    )
    async with db.execute(
        "SELECT * FROM fix_proposals WHERE id = ?", (proposal["id"],)
    ) as cursor:
        stored = await cursor.fetchone()
    await ai_fix.approve_proposal(db, stored, actor="approver")
    await db.commit()


@pytest.mark.asyncio
async def test_sync_reapplies_overlay_when_pipeline_output_is_unchanged(
    runtime_sandbox, gateway
):
    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        await _approve_fix(db, document_id, section_id)
    finally:
        await db.close()

    # Pipeline output on disk is unchanged; force pushes it through create_version.
    await run_sync(runtime_sandbox["root"] / "export", force=True)

    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT plain_text, review_status FROM sections WHERE id = ?",
            (section_id,),
        ) as cursor:
            section = await cursor.fetchone()
        assert section["plain_text"] == FIXED_TEXT
        assert section["review_status"] == "approved"
        async with db.execute(
            "SELECT status FROM section_overlays"
        ) as cursor:
            assert (await cursor.fetchone())["status"] == "active"


@pytest.mark.asyncio
async def test_sync_marks_overlay_stale_when_pipeline_leaf_changed(
    runtime_sandbox, gateway
):
    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        await _approve_fix(db, document_id, section_id)
    finally:
        await db.close()

    # The parser was improved: its output for that leaf no longer matches the
    # leaf the fix was approved against. The pipeline wins; the overlay dies.
    source = runtime_sandbox["root"] / "export"
    (source / "Test Act" / "act.json").write_text(
        sample_document(second_text="Second section, fixed by the parser"),
        encoding="utf-8",
    )
    await run_sync(source)

    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT plain_text, review_status FROM sections WHERE id = ?",
            (section_id,),
        ) as cursor:
            section = await cursor.fetchone()
        assert section["plain_text"] == "Second section, fixed by the parser"
        assert section["review_status"] == "has_issues"
        async with db.execute("SELECT status FROM section_overlays") as cursor:
            assert (await cursor.fetchone())["status"] == "stale"


@pytest.mark.asyncio
async def test_sync_supersedes_overlay_when_pipeline_catches_up(
    runtime_sandbox, gateway
):
    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        await _approve_fix(db, document_id, section_id)
    finally:
        await db.close()

    # The parser now produces exactly what the fix said. Retire the overlay.
    source = runtime_sandbox["root"] / "export"
    payload = json.loads(sample_document())
    leaf = payload["chapters"][0]["sections"][1]
    leaf["plain_text"] = FIXED_TEXT
    leaf["html"] = FIXED_HTML
    (source / "Test Act" / "act.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    await run_sync(source)

    async with aiosqlite.connect(runtime_sandbox["db_path"]) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT plain_text FROM sections WHERE id = ?", (section_id,)
        ) as cursor:
            assert (await cursor.fetchone())["plain_text"] == FIXED_TEXT
        async with db.execute("SELECT status FROM section_overlays") as cursor:
            assert (await cursor.fetchone())["status"] == "superseded"


# ---------------------------------------------------------------------------
# route guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_models_route_returns_the_dropdown_list(runtime_sandbox, gateway):
    from backend.routes.ai_fixes import list_models

    response = await list_models()
    assert response.models == ["test-model", "second-model"]
    assert response.default == "test-model"


@pytest.mark.asyncio
async def test_request_route_returns_503_when_unconfigured(
    runtime_sandbox, monkeypatch
):
    from fastapi import HTTPException

    from backend.models import FixProposalCreate
    from backend.routes.ai_fixes import request_ai_fix

    for name in (
        "OPENPATHS_API_KEY",
        "OPENPATHS_BASE_URL",
        "OPENPATHS_MODEL",
        "OPENPATHS_MODELS",
        "LLM_EXTRA_PROVIDERS",
    ):
        monkeypatch.delenv(name, raising=False)

    db, document_id, section_id = await synced_document(runtime_sandbox)
    try:
        with pytest.raises(HTTPException) as excinfo:
            await request_ai_fix(
                document_id,
                section_id,
                FixProposalCreate(instructions="fix"),
                db=db,
                actor="tester",
            )
        assert excinfo.value.status_code == 503
    finally:
        await db.close()

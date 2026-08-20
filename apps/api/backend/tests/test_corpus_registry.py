"""The corpus registry, and the two request shapes that select against it.

Adding a third corpus used to mean editing a two-element hardcode in eight places.
These pin the parts that are easy to get subtly wrong: which corpora a selector picks,
in what order, and what happens to a label nobody recognises.
"""

from __future__ import annotations

import pytest

from backend.routes.corpus import SyncRequest
from backend.services import corpus_registry as registry


def test_registry_lists_every_corpus_in_order():
    assert registry.LABELS == ("ordinance", "acts", "rules")
    assert [c.label for c in registry.CORPORA] == list(registry.LABELS)
    assert [c.env for c in registry.CORPORA] == [
        "CORPUS_ORDINANCE",
        "CORPUS_ACTS",
        "CORPUS_RULES",
    ]


def test_path_follows_the_environment_then_falls_back(monkeypatch):
    monkeypatch.setenv("CORPUS_RULES", "/mnt/somewhere/rules")
    assert str(registry.get("rules").path()) == "/mnt/somewhere/rules"
    monkeypatch.delenv("CORPUS_RULES")
    assert registry.get("rules").path().name == "rules"
    assert registry.get("rules").path().is_absolute()


def test_selection_uses_registry_order_not_caller_order():
    """Sync order is ordinance, acts, rules regardless of how a caller lists them."""
    assert [c.label for c in registry.selected(["rules", "ordinance"])] == [
        "ordinance",
        "rules",
    ]
    assert [c.label for c in registry.selected()] == list(registry.LABELS)
    assert [c.label for c in registry.selected([])] == []


def test_an_unknown_corpus_raises_rather_than_syncing_everything():
    """A misspelt --rules-only must not quietly become "sync all three"."""
    with pytest.raises(ValueError, match="nope"):
        list(registry.selected(["acts", "nope"]))


def test_mount_health_requires_output_json(tmp_path):
    root = tmp_path / "rules"
    (root / "output").mkdir(parents=True)
    assert registry.corpus_root_configured(root) is False
    (root / "output" / "x.json").write_text("{}", encoding="utf-8")
    assert registry.corpus_root_configured(root) is True
    assert registry.corpus_root_configured(None) is False
    assert registry.corpus_root_configured(tmp_path / "absent") is False


@pytest.mark.parametrize(
    "body,expected",
    [
        (SyncRequest(), ["ordinance", "acts", "rules"]),
        (SyncRequest(only=["rules"]), ["rules"]),
        (SyncRequest(only=["rules", "ordinance"]), ["ordinance", "rules"]),
        (SyncRequest(rules_only=True), ["rules"]),
        (SyncRequest(acts_only=True), ["acts"]),
        # the legacy flags still work, and `only` wins when both are given
        (SyncRequest(only=["acts"], rules_only=True), ["acts"]),
    ],
)
def test_sync_request_selection(body, expected):
    assert body.wanted() == expected


def test_sync_request_rejects_an_unknown_corpus():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        SyncRequest(only=["ordnance"]).wanted()
    assert excinfo.value.status_code == 400
    assert "ordnance" in excinfo.value.detail


async def test_status_endpoint_describes_every_corpus(client):
    """The Library subtitle reads `corpora`; the flat fields are the old shape.

    A corpus missing from the response is a corpus the operator cannot see is
    unmounted, which is exactly the confusion the subtitle exists to prevent.
    """
    response = await client.get("/api/corpus/status")
    assert response.status_code == 200
    body = response.json()

    assert [c["label"] for c in body["corpora"]] == list(registry.LABELS)
    for entry in body["corpora"]:
        assert entry["title"]
        assert entry["path"]
        assert isinstance(entry["configured"], bool)
        assert entry["documents"] == 0

    # the pre-registry fields still answer, for a frontend deployed ahead of the API
    ordinance = next(c for c in body["corpora"] if c["label"] == "ordinance")
    assert body["ordinance_path"] == ordinance["path"]
    assert body["ordinance_configured"] == ordinance["configured"]


async def test_sync_refuses_a_corpus_that_is_not_mounted(client):
    """Naming the corpus matters: "not mounted" alone does not say which one."""
    response = await client.post("/api/corpus/sync", json={"only": ["rules"]})
    assert response.status_code == 400
    assert "Rules pipeline mount not on this host" in response.json()["detail"]


async def test_sync_rejects_an_unknown_corpus_label(client):
    response = await client.post("/api/corpus/sync", json={"only": ["ordnance"]})
    assert response.status_code == 400
    assert "ordnance" in response.json()["detail"]


def test_no_collisions_in_the_real_corpora():
    """The live trees must not already share a stem -- if they do, syncing loses one."""
    from backend.services.corpus_sync import source_key_collisions

    assert source_key_collisions() == {}


def test_a_shared_json_stem_is_detected(monkeypatch, tmp_path):
    """Two corpora, one stem: both documents resolve to a single id."""
    from backend.services.corpus_sync import source_key_collisions
    from backend.sync_acts import deterministic_document_id

    acts, rules = tmp_path / "acts", tmp_path / "rules"
    for root in (acts, rules):
        (root / "output").mkdir(parents=True)
        (root / "output" / "Widget Law, 2001.json").write_text("{}", encoding="utf-8")
    (acts / "output" / "unique-to-acts.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("CORPUS_ORDINANCE", str(tmp_path / "absent"))
    monkeypatch.setenv("CORPUS_ACTS", str(acts))
    monkeypatch.setenv("CORPUS_RULES", str(rules))

    assert source_key_collisions() == {"Widget Law, 2001": ["acts", "rules"]}
    # why it matters: the id derives from the stem alone
    assert deterministic_document_id("Widget Law, 2001") == deterministic_document_id(
        "Widget Law, 2001"
    )


async def test_sync_refuses_to_run_with_a_collision(monkeypatch, tmp_path):
    """Refusing beats syncing: the loser is overwritten with no trace."""
    from backend.services.corpus_sync import run_corpus_sync

    acts, rules = tmp_path / "acts", tmp_path / "rules"
    for root in (acts, rules):
        (root / "output").mkdir(parents=True)
        (root / "output" / "Same Stem.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CORPUS_ORDINANCE", str(tmp_path / "absent"))
    monkeypatch.setenv("CORPUS_ACTS", str(acts))
    monkeypatch.setenv("CORPUS_RULES", str(rules))

    # even syncing one corpus is refused -- it can still clobber the other's document
    with pytest.raises(ValueError, match="Same Stem"):
        await run_corpus_sync(only=["rules"], dry_run=True)


async def test_an_unmounted_corpus_skips_a_blanket_sync(monkeypatch, tmp_path):
    """"Sync everything" must not fail because a corpus is not staged here.

    Rules is absent on CI, on every deployment, and in any checkout that has not
    vendored it. Counting that as a failure makes every default sync red and trains
    people to ignore the result.
    """
    from backend.services.corpus_sync import run_corpus_sync

    acts = tmp_path / "acts"
    (acts / "output").mkdir(parents=True)
    monkeypatch.setenv("CORPUS_ORDINANCE", str(tmp_path / "absent-ordinance"))
    monkeypatch.setenv("CORPUS_ACTS", str(acts))
    monkeypatch.setenv("CORPUS_RULES", str(tmp_path / "absent-rules"))

    summary = await run_corpus_sync(dry_run=True)
    assert summary["failed"] == 0
    for label in ("ordinance", "acts", "rules"):
        assert summary[label]["skipped_corpus"] == "not mounted on this host"


async def test_asking_for_an_unmounted_corpus_is_still_an_error(monkeypatch, tmp_path):
    """Silence would look like success on a sync that imported nothing."""
    from backend.services.corpus_sync import run_corpus_sync

    monkeypatch.setenv("CORPUS_RULES", str(tmp_path / "absent-rules"))
    summary = await run_corpus_sync(only=["rules"], dry_run=True)
    assert summary["failed"] == 1  # one missing corpus, counted once
    assert "does not exist" in summary["rules"]["error"]


async def test_every_corpus_appears_in_the_summary(monkeypatch, tmp_path):
    """"Synced nothing" and "was not asked to" must be distinguishable."""
    from backend.services.corpus_sync import run_corpus_sync

    monkeypatch.setenv("CORPUS_ORDINANCE", str(tmp_path / "a"))
    monkeypatch.setenv("CORPUS_ACTS", str(tmp_path / "b"))
    monkeypatch.setenv("CORPUS_RULES", str(tmp_path / "c"))

    summary = await run_corpus_sync(only=["acts"], dry_run=True)
    assert set(registry.LABELS) <= set(summary)
    assert summary["ordinance"] == {} and summary["rules"] == {}
    assert summary["acts"]

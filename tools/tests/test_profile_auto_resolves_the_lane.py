"""``--profile auto`` must not throw away the profile the lane already knows.

The bug this locks (``wip/phase2-findings.md`` finding 1): ``families.py``
hardcoded ``consolidated -> ACTS`` and ``convert.py`` passed ``profile=None``,
which overrode the ``partial(pipeline.run, profile=RULES)`` binding in
``rules_ingest``.  A Phase 2 re-conversion would then have parsed all 34
consolidated Rules documents as Acts, across 12 fields of parsing behaviour --
five hours of OCR spent producing worse output than the run it replaced.

It asserts over the REAL corpus without needing the corpus: every signature in
``tools/discovery/signatures.json`` is committed, so ``Signature(**record)``
reconstructs the measurement and the resolution runs on it.  No PDFs, nothing
gitignored -- unlike the lane suites, this one actually runs on CI.
"""

from __future__ import annotations

import json

import pytest

import corpus_paths  # noqa: F401  (sys.path bootstrap: puts packages/ on the path)
from legal_ingest import pipeline
from legal_ingest.families import BY_LABEL
from legal_ingest.profiles import ACTS, AMENDING, RULES
from legal_ingest.signature import Signature

SIGNATURES = corpus_paths.REPO_ROOT / "tools" / "discovery" / "signatures.json"

#: The profile each lane binds today -- acts_ingest.PROFILE / rules_ingest.PROFILE,
#: named here rather than imported so the test does not depend on the parse stack
#: those packages pull in.  The ordinance lane has none: fbr_ingest takes no
#: profile at all, which is why --profile auto is refused there up front.
LANE_PROFILE = {"acts": ACTS, "rules": RULES}


def _records(lane: str, family: str) -> list[dict]:
    """Committed signatures for one lane and family, MEASURED ones only.

    A record whose ``source`` is ``group`` was placed by group inheritance,
    which is a census-wide fact: nine Finance Act scans are recorded ``amending``
    because every text-bearing edition in their folder is.  ``pipeline.run``
    classifies ONE document with no group context, so it sees those as
    ``no_text_layer`` and refuses them -- correctly, since they cannot be parsed
    without OCR either way.
    """
    records = json.loads(SIGNATURES.read_text(encoding="utf-8"))["records"]
    return [r for r in records if r["lane"] == lane
            and r["assignment"]["family"] == family
            and r["assignment"]["source"] == "measured"]


def _resolve(record: dict, monkeypatch):
    sig = Signature(**record["signature"])
    monkeypatch.setattr("legal_ingest.signature.measure", lambda *a, **k: sig)
    profile, _ = pipeline._resolve_profile(
        record["signature"]["path"], LANE_PROFILE[record["lane"]], lambda *a: None)
    return profile


@pytest.mark.parametrize("lane,family,expected", [
    ("rules", "consolidated", RULES),   # the regression: was resolving ACTS
    ("acts", "consolidated", ACTS),
    ("acts", "amending", AMENDING),     # the one family that DOES override
])
def test_every_document_resolves_to_the_right_profile(lane, family, expected,
                                                      monkeypatch):
    records = _records(lane, family)
    assert records, f"no committed {lane}/{family} signatures to test"
    wrong = [r["signature"]["path"] for r in records
             if _resolve(r, monkeypatch) is not expected]
    assert not wrong, f"{len(wrong)} {lane} documents resolved wrongly: {wrong[:3]}"


def test_a_family_that_cannot_be_parsed_is_refused_not_defaulted(monkeypatch):
    """Refusal is now ``parseable``, not ``profile is None``.

    With the profile field carrying only the override, a refused family reads
    ``profile=None`` exactly as ``consolidated`` does -- so if refusal were still
    read off it, an Urdu edition would silently parse with the lane's profile.
    """
    for family in ("urdu", "no_text_layer", "unconvertible"):
        assert not BY_LABEL[family].parseable
        records = _records("acts", family) or _records("ordinance", family)
        if not records:
            continue
        record = dict(records[0], lane="acts")
        with pytest.raises(RuntimeError, match="is not parseable"):
            _resolve(record, monkeypatch)


def test_only_amending_overrides_the_lane():
    """Every other family defers, which is what makes the lane binding the answer."""
    overriding = {f.label for f in BY_LABEL.values() if f.profile is not None}
    assert overriding == {"amending"}

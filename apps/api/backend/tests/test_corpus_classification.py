"""The two existing corpora must not be reclassified by accident.

``corpus_lane`` decides which Library facet a document appears under, and
``family_key_from_name`` decides which editions group together as one statute -- and,
since the PostgreSQL migration, it also keys the ``statute_families`` row that
``services.identity.persist_inferred_identity`` writes on every version. A change to
either function silently reshapes the Library and mints new family rows.

Both functions are about to be extended for a third corpus (Rules), so this pins what
they currently return for all 92 Ordinance and Acts documents. The fixture is names
only -- statute titles, no corpus content -- so it runs in CI, where the corpus itself
is absent.

When a change here is intended, regenerate the fixture and review the diff. An
unexplained line in that diff is the bug this file exists to catch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services.corpus_lanes import LANE_ORDER, classify_lane
from backend.services.editions import edition_date_from_name, family_key_from_name

FIXTURE = Path(__file__).parent / "fixtures" / "corpus_classification.json"
RECORDED = json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_covers_the_whole_corpus():
    assert len(RECORDED) == 92, "regenerate the fixture if the corpus changed size"
    assert len({row["name"] for row in RECORDED}) == len(RECORDED), "duplicate names"


@pytest.mark.parametrize("row", RECORDED, ids=lambda row: row["name"])
def test_classification_is_unchanged(row):
    assert (
        classify_lane(
            row["name"],
            source_type="acts_corpus",
            corpus_origin=row["corpus_origin"],
        )
        == row["lane"]
    )
    assert family_key_from_name(row["name"]) == row["family_key"]
    assert edition_date_from_name(row["name"])["year"] == row["edition_year"]


def test_every_recorded_lane_is_a_known_lane():
    """A lane the UI does not list is a document that vanishes from the Source facet.

    ``normalize_lane`` rejects anything outside ``LANE_ORDER``, and
    ``routes.documents._resolve_corpus_lane`` then reclassifies the row by name on
    every read -- so an unlisted lane is not a cosmetic problem.
    """
    assert {row["lane"] for row in RECORDED} <= set(LANE_ORDER)

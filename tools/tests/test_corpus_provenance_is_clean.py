"""No staged document may carry a ``-dirty`` pipeline revision.

``legal_contract.pipeline_revision`` marks a conversion made from a tree with
uncommitted changes, because the field answers "which parser wrote this" and a
dirty tree cannot answer it.  Round 35 stamped all 77 documents
``8032b142c72f-dirty`` and it cost a second 16-minute run; round 38 left 21 acts
editions ``a8a0dffe4bf9-dirty`` and **nothing noticed for a day** -- the register,
the lane suites and the pipeline gate all read content, and the content was right.

So this is the one check that reads the provenance instead.  It is deliberately
narrower than "the corpus is at one revision", which can never be true: the 14
image-backed acts editions and the 3 image-backed ITO editions cannot be
re-converted under the standing no-OCR decision, and the ordinance lane runs a
separate parser.  Those are *stale*, which is recorded and attributable.
``-dirty`` is never attributable, in any lane, at any age.

``data/corpora/*/output/`` is gitignored, so this skips on CI exactly as the lane
suites and ``test_register_snapshot.py`` do.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tools"))
from corpus_paths import LABELS, output_dir  # noqa: E402


def _staged() -> list[pathlib.Path]:
    """Every staged output, across the lanes.  ``_pre_*``/``_run`` are subdirs."""
    return [p for lane in LABELS for p in sorted(output_dir(lane).glob("*.json"))]


def test_no_staged_output_was_converted_from_a_dirty_tree() -> None:
    staged = _staged()
    if not staged:
        pytest.skip("corpus not staged -- the lane suites skip here too")
    dirty = []
    for path in staged:
        revision = json.loads(path.read_text()).get("metadata", {}).get("pipeline_revision")
        if (revision or "").endswith("-dirty"):
            dirty.append(f"{path.parent.parent.name}/{path.name}: {revision}")
    assert not dirty, (
        f"{len(dirty)} of {len(staged)} staged documents were converted from a dirty "
        "tree, so their provenance is unusable -- re-convert them from a clean tree:\n  "
        + "\n  ".join(dirty)
    )

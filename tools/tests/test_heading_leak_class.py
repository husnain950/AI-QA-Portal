"""Parser self-checks for the Customs 14A heading-leak class.

The corpus PDFs are gitignored; these pin the grammar on documented shapes.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from legal_ingest import builder, grammar, pagemodel, pipeline, toc  # noqa: E402


def test_legal_ingest_demos_for_heading_leak_class():
    toc._demo()
    builder._demo()
    pagemodel._demo()
    grammar._demo()
    pipeline._demo()


def test_scan_heading_leaks_skips_without_corpus():
    """The no-corpus path, and ONLY that path.

    It used to assert ``main(["acts"]) == 0`` unconditionally, which is true only
    where the corpus is absent. With it staged the scan correctly returns
    non-zero -- 144 hits across 80 files, measured 2026-08-29 -- so this was
    green on CI and red on every developer machine that actually has the data,
    the exact inversion this project already knows about (recorded in
    wip/tasks.md under Phase 1).
    """
    from corpus_paths import output_dir
    from scan_heading_leaks import main

    if any(output_dir("acts").glob("*.json")):
        pytest.skip("acts corpus is staged -- the scan reports its hits, as it should")
    assert main(["acts"]) == 0

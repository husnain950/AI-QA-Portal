"""Parser self-checks for the Customs 14A heading-leak class.

The corpus PDFs are gitignored; these pin the grammar on documented shapes.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from legal_ingest import builder, grammar, pagemodel, pipeline, toc  # noqa: E402


def test_legal_ingest_demos_for_heading_leak_class():
    toc._demo()
    builder._demo()
    pagemodel._demo()
    grammar._demo()
    pipeline._demo()


def test_scan_heading_leaks_skips_without_corpus():
    from scan_heading_leaks import main

    assert main(["acts"]) == 0

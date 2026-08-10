#!/usr/bin/env python3
"""Thin wrapper: import QA report findings into pipeline regression cases."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
target = ROOT / "tools" / "ordinance" / "import_qa_report.py"
if not target.exists():
    target = ROOT / "tools" / "acts" / "add_test_case.py"
sys.argv[0] = str(target)
runpy.run_path(str(target), run_name="__main__")

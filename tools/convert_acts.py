#!/usr/bin/env python3
"""Convert an Acts PDF using packages/acts_ingest."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

_SCRIPT = ROOT / "tools" / "acts" / "acts_pdf_to_json.py"
spec = importlib.util.spec_from_file_location("crx_convert_acts", _SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
raise SystemExit(module.main())

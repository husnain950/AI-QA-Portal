#!/usr/bin/env python3
"""Corpus-wide legal HTML fidelity gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from backend.services.html_sanitizer import sanitize_html  # noqa: E402


def html_values(value: Any, pointer: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{pointer}/{key}"
            if key == "html" and isinstance(item, str):
                yield child, item
            yield from html_values(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from html_values(item, f"{pointer}/{index}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="+", type=Path)
    args = parser.parse_args()
    files = []
    for root in args.roots:
        files.extend(root.rglob("*.json") if root.is_dir() else [root])
    checked = changed = 0
    failures = []
    diagnostics: dict[str, int] = {}
    for path in sorted(set(files)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            failures.append({"file": str(path), "pointer": "/", "error": str(exc)})
            continue
        for pointer, source in html_values(data):
            checked += 1
            result = sanitize_html(source)
            changed += int(result.changed)
            for diagnostic in result.diagnostics:
                diagnostics[diagnostic] = diagnostics.get(diagnostic, 0) + 1
            if not result.text_fidelity or not result.structure_fidelity:
                failures.append(
                    {
                        "file": str(path),
                        "pointer": pointer,
                        "text_fidelity": result.text_fidelity,
                        "structure_fidelity": result.structure_fidelity,
                    }
                )
    summary = {
        "files": len(set(files)),
        "html_fragments": checked,
        "changed_fragments": changed,
        "failures": len(failures),
        "diagnostics": diagnostics,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if failures:
        print(json.dumps(failures[:50], indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

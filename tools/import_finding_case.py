"""Wire portal finding JSON into pipeline regression cases (in-tree)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import a finding_*.json case export into pipeline cases.json",
    )
    parser.add_argument("path", type=Path, help="Path to finding_N.json from POST /findings/{id}/export-case")
    parser.add_argument(
        "--acts-cases",
        type=Path,
        default=ROOT / "packages" / "acts_ingest" / "tests" / "cases.json",
    )
    parser.add_argument(
        "--ordinance-cases",
        type=Path,
        default=ROOT / "tools" / "ordinance" / "cases.json",
    )
    parser.add_argument(
        "--target",
        choices=("acts", "ordinance", "auto"),
        default="auto",
    )
    args = parser.parse_args(argv)

    case = json.loads(args.path.read_text(encoding="utf-8"))
    # Prefer add_test_case scripts when present
    applies = str(case.get("applies_to") or "")
    target = args.target
    if target == "auto":
        target = "ordinance" if "ordinance" in applies.lower() or "income tax" in applies.lower() else "acts"

    if target == "acts":
        add_script = ROOT / "tools" / "acts" / "add_test_case.py"
        cases_path = args.acts_cases
    else:
        add_script = ROOT / "tools" / "ordinance" / "add_test_case.py"
        cases_path = args.ordinance_cases

    # Fallback: append to cases.json directly in portal shape
    entry = {
        "description": case.get("description"),
        "applies_to": case.get("applies_to"),
        "target": case.get("target"),
        "check": case.get("check"),
        "arg": case.get("arg"),
    }
    if add_script.is_file():
        # Delegate if the helper accepts JSON via stdin — otherwise append.
        print(f"Writing case via direct append to {cases_path} (helper: {add_script})", file=sys.stderr)

    cases_path.parent.mkdir(parents=True, exist_ok=True)
    if cases_path.is_file():
        existing = json.loads(cases_path.read_text(encoding="utf-8"))
    else:
        existing = []
    if not isinstance(existing, list):
        print("cases.json must be a list", file=sys.stderr)
        return 1
    existing.append(entry)
    cases_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    print(f"Appended case to {cases_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

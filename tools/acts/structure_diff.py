#!/usr/bin/env python3
"""Snapshot every edition's structure, then prove a change did not lose any.

Built for P06.  The fix there has to REJECT section starts that the clause
cursor should never have accepted, and the failure mode of any such rule is
silent: it drops a real section and every other check stays green, because the
invariants test the shape of what is present and conservation is measured on
text that a dropped heading still carries in its parent.  The only way to know
is to compare the whole structure before and after, section by section.

    python scripts/structure_diff.py --save before.json
    ... make the change, reconvert ...
    python scripts/structure_diff.py --against before.json

Exit 1 when any section disappeared and is not listed in the drop-list, so this
can gate a landing.  A drop-list entry is a REVIEWED decision -- "this code was
never a section of this Act" -- and it names the edition and the code, so the
reviewing is visible in the diff instead of buried in a threshold.

    python scripts/structure_diff.py --against before.json --drops drops.json

`drops.json` is `{"<edition stem>": ["65G", "203C", ...]}`.
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "output"


def _leaves(node):
    for s in node.get("sections") or []:
        yield s
    for key in ("parts", "divisions"):
        for child in node.get(key) or []:
            yield from _leaves(child)


def snapshot(out_dir: pathlib.Path = OUT) -> dict:
    """``{edition: {code: heading}}`` over chapters only.

    Schedules are excluded deliberately: their codes are not clause numbers and
    they move for unrelated reasons, which would bury the signal this exists to
    show.
    """
    snap = {}
    for jf in sorted(out_dir.glob("*.json")):
        try:
            doc = json.loads(jf.read_text(encoding="utf-8"))
        except ValueError:
            continue
        secs = {}
        for ch in doc.get("chapters") or []:
            for s in _leaves(ch):
                secs[str(s.get("code"))] = (s.get("heading") or "").strip()[:120]
        snap[jf.stem] = secs
    return snap


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save", help="write a snapshot of output/ to this path")
    ap.add_argument("--against", help="compare output/ against this snapshot")
    ap.add_argument("--drops", help="JSON of reviewed, permitted removals")
    args = ap.parse_args(argv)

    now = snapshot()
    if args.save:
        pathlib.Path(args.save).write_text(
            json.dumps(now, indent=1, ensure_ascii=False), encoding="utf-8")
        n = sum(len(v) for v in now.values())
        print(f"snapshot: {len(now)} editions, {n} sections -> {args.save}")
        return 0

    if not args.against:
        ap.error("one of --save or --against is required")
    before = json.loads(pathlib.Path(args.against).read_text(encoding="utf-8"))
    allowed = {}
    if args.drops:
        allowed = json.loads(pathlib.Path(args.drops).read_text(encoding="utf-8"))

    unreviewed = 0
    for name in sorted(set(before) | set(now)):
        was, is_ = before.get(name), now.get(name)
        if is_ is None:
            print(f"  GONE     {name}  (edition no longer in output/)")
            unreviewed += 1
            continue
        if was is None:
            print(f"  NEW EDN  {name}  ({len(is_)} sections)")
            continue
        lost = [c for c in was if c not in is_]
        gained = [c for c in is_ if c not in was]
        ok = set(allowed.get(name) or [])
        bad = [c for c in lost if c not in ok]
        if not (lost or gained):
            continue
        print(f"  {name}  ({len(was)} -> {len(is_)} sections)")
        for c in lost:
            tag = "dropped (reviewed)" if c in ok else "DROPPED"
            print(f"      - {c:>8}  {tag}: {was[c][:70]}")
        for c in gained:
            print(f"      + {c:>8}  gained: {is_[c][:70]}")
        unreviewed += len(bad)

    print(f"\nRESULT: {'OK' if not unreviewed else f'{unreviewed} UNREVIEWED REMOVAL(S)'}")
    return 1 if unreviewed else 0


if __name__ == "__main__":
    raise SystemExit(main())

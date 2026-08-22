"""Shared helpers for loading a converted JSON and locating nodes within it.

The regression suite runs against an already-generated output JSON (fast).  Use
``run_tests.py --pdf <PDF>`` to regenerate first, or point it at any JSON.
"""

from __future__ import annotations

import json


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def iter_section_leaves(doc: dict):
    """Yield every chapter-side section leaf (has a ``plain_text``)."""
    for ch in doc.get("chapters", []):
        yield from _iter_leaves(ch)


def iter_schedule_leaves(doc: dict):
    for sc in doc.get("schedules", []):
        yield from _iter_leaves(sc)


def iter_all_leaves(doc: dict):
    yield from iter_section_leaves(doc)
    yield from iter_schedule_leaves(doc)


def _iter_leaves(node: dict):
    if not isinstance(node, dict):
        return
    if "plain_text" in node:
        yield node
    for key in ("parts", "divisions", "sections"):
        for child in node.get(key, []):
            yield from _iter_leaves(child)


def find_section(doc: dict, code: str):
    """First chapter-side section leaf with the given code."""
    for leaf in iter_section_leaves(doc):
        if str(leaf.get("code")) == str(code):
            return leaf
    return None


def find_schedule(doc: dict, code_contains: str):
    """First schedule whose code contains ``code_contains`` (case-insensitive)."""
    cc = code_contains.upper()
    for sc in doc.get("schedules", []):
        if cc in str(sc.get("code", "")).upper():
            return sc
    return None


def find_leaf(doc: dict, kind: str, code: str):
    """Locate a target node for a case.

    kind == 'section'        -> chapter section leaf by code
    kind == 'schedule'       -> schedule root by (partial) code
    kind == 'schedule_leaf'  -> any leaf under a schedule whose code matches
    """
    if kind == "section":
        return find_section(doc, code)
    if kind == "schedule":
        return find_schedule(doc, code)
    if kind == "schedule_leaf":
        sc = find_schedule(doc, code)
        if sc is None:
            return None
        leaves = list(_iter_leaves(sc))
        return leaves[0] if leaves else None
    return None


def all_footnotes(doc: dict):
    for leaf in iter_all_leaves(doc):
        for fn in leaf.get("footnotes", []):
            yield leaf, fn


def find_footnote(doc: dict, ref: str):
    for _leaf, fn in all_footnotes(doc):
        if fn.get("ref") == ref:
            return fn
    return None


def html_fragments(doc: dict):
    """Yield ('label', html) for every html string in the document."""
    for leaf in iter_all_leaves(doc):
        code = leaf.get("code", "?")
        yield (f"section {code}", leaf.get("html", ""))
        for fn in leaf.get("footnotes", []):
            yield (f"footnote {fn.get('ref')}", fn.get("html", ""))

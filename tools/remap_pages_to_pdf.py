#!/usr/bin/env python3
"""Re-page a Word-derived export against the PDF it will be reviewed beside.

    python tools/remap_pages_to_pdf.py <export.json> <rendered.pdf>

A Word export carries Word's own pagination -- the saved page breaks of a ``.docx``,
or a character-share estimate for a ``.doc`` -- but the portal has no PDF for it until
one is rendered, and LibreOffice does not paginate like Word. Measured on the
2026-09-25 export, the gap grows through the document: Income Tax Ordinance s.114 is
declared p210 and prints on p224, s.236G p454 and p487. The review pane would open
the wrong page for nearly every leaf.

So every leaf is looked up by its heading (``code`` + ``heading``, else the first
substantial line of ``plain_text``) in the rendered text, near where the running
offset says it should be and never before the leaf above it. Contents pages are not
candidates: every heading is printed there too, and LibreOffice lays a Word contents
field out far longer than Word did (Sales Tax Rules 2006: 16 pages, putting rule 1 13
pages past its declared page). A leaf whose heading is not found keeps the offset of
the last one that was. A leaf whose declared page is a default rather than a position
-- far behind a page already passed in tree order -- is placed only where its heading
prints exactly once, and otherwise left as declared. End pages follow the next leaf's
start, and footnote pages move with their leaf. The JSON is rewritten in place;
nothing else in it changes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

#: How far from the expected page a heading may be found. The offset is re-read at
#: every located leaf, so this only has to cover the drift between two neighbours.
WINDOW = 12
#: Shorter keys ("str1", "firstschedule") match cross-references all over the body.
MIN_KEY = 14
#: A page naming this many leaves' headings is contents, not body. On the 2026-09-25
#: export every contents page names 10-30 and no body page more than 8.
CONTENTS_MIN = 10


def compact(text: str | None) -> str:
    return re.sub(r"[^0-9a-z]+", "", (text or "").lower())


def keys_for(leaf: dict) -> list[str]:
    """The strings that identify a leaf on its first page, best first."""
    keys = []
    if (leaf.get("heading") or "").strip():
        keys.append(compact(f"{leaf.get('code') or ''}{leaf['heading']}")[:40])
    for line in (leaf.get("plain_text") or "").splitlines():
        if len(compact(line)) >= MIN_KEY:
            keys.append(compact(line)[:40])
            break
    return [key for key in keys if len(key) >= MIN_KEY]


def leaves_in_page_order(data: dict) -> list[tuple[dict, bool]]:
    """Every paged node that carries html, ordered by its declared page.

    Paired with whether that page is a position to walk from. The 2026-09-25 export
    declares Income Tax Ordinance's Division IX and Twelfth Schedule parts, and Sales
    Tax Rules 2006's six omitted chapters, on page 1: Word saved no page break for them.
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            if "html" in node and isinstance(node.get("start_page") or node.get("page_number"), int):
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk({key: value for key, value in data.items() if key != "metadata"})
    high, flagged = 0, []
    for leaf in found:
        page = leaf.get("start_page") or leaf["page_number"]
        flagged.append((leaf, page >= high - WINDOW))
        high = max(high, page)
    # Stable, so leaves declared on one page keep the tree's order.
    return sorted(flagged, key=lambda item: item[0].get("start_page") or item[0]["page_number"])


def _move(leaf: dict, start: int, new_start: int, new_end: int) -> None:
    """Set a leaf's pages; its footnotes move with it and stay inside it."""
    leaf["start_page"], leaf["end_page"] = new_start, new_end
    if "page_number" in leaf:
        leaf["page_number"] = new_start
    for footnote in leaf.get("footnotes") or []:
        if isinstance(footnote.get("page"), int):
            footnote["page"] = min(max(footnote["page"] + new_start - start, new_start), new_end)


def remap(data: dict, pages: list[str]) -> dict:
    """Rewrite page fields in ``data`` against ``pages`` (compacted page texts)."""
    keyed = [(leaf, keys_for(leaf), walkable) for leaf, walkable in leaves_in_page_order(data)]
    headings = {keys[0] for _, keys, _ in keyed if keys}
    contents = {
        number for number, text in enumerate(pages, 1)
        if sum(key in text for key in headings) >= CONTENTS_MIN
    }
    total = len(pages)
    offset, cursor, located = 0, 1, 0
    placed = []  # (leaf, declared_start, declared_end, new_start)
    for leaf, keys, walkable in keyed:
        if not walkable:
            continue
        start = leaf.get("start_page") or leaf["page_number"]
        end = leaf.get("end_page") or start
        expected = start + offset
        # Until one leaf is found the front matter's offset is unknown, so look wider.
        window = WINDOW if located else 3 * WINDOW
        hit = None
        for key in keys:
            candidates = [
                page for page in range(max(cursor, expected - window), min(total, expected + window) + 1)
                if page not in contents and key in pages[page - 1]
            ]
            if candidates:
                hit = min(candidates, key=lambda page: abs(page - expected))
                break
        if hit is None:
            new_start = min(max(expected, cursor), total)
        else:
            new_start, offset, located = hit, hit - start, located + 1
        cursor = new_start
        placed.append((leaf, start, end, new_start))

    for index, (leaf, start, end, new_start) in enumerate(placed):
        if index + 1 < len(placed):
            _, next_start, _, next_new = placed[index + 1]
            # Sharing a page with the next leaf in Word means sharing one here.
            new_end = next_new if end >= next_start else next_new - 1
        else:
            new_end = new_start + (end - start)
        _move(leaf, start, new_start, min(max(new_end, new_start), total))

    for leaf, keys, walkable in keyed:
        if walkable:
            continue
        hits = next(
            (found for found in (
                [page for page in range(1, total + 1)
                 if page not in contents and key in pages[page - 1]]
                for key in keys
            ) if found),
            [],
        )
        if len(hits) == 1:
            start = leaf.get("start_page") or leaf["page_number"]
            span = (leaf.get("end_page") or start) - start
            _move(leaf, start, hits[0], min(hits[0] + span, total))
            located += 1

    meta = data.setdefault("metadata", {})
    meta["total_pages"] = total
    meta["page_numbers"] = (
        f"remapped to the rendered PDF by heading ({located} of {len(keyed)} leaves "
        f"located, the rest carried from the last located)"
    )
    return {"leaves": len(keyed), "located": located, "contents_pages": len(contents)}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    from pypdf import PdfReader

    json_path, pdf_path = Path(argv[0]), Path(argv[1])
    data = json.loads(json_path.read_text(encoding="utf-8"))
    pages = [compact(page.extract_text()) for page in PdfReader(str(pdf_path)).pages]
    result = remap(data, pages)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{json_path.name}: {result['located']}/{result['leaves']} leaves located, "
          f"{len(pages)} pages, {result['contents_pages']} contents pages skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

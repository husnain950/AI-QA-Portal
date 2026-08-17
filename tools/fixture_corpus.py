#!/usr/bin/env python3
"""Generate a deterministic micro-corpus for review-page smoke testing.

The real corpora under ``data/corpora/`` are gitignored and absent from a fresh clone,
so ``make sync`` has nothing to load and every review-page assertion has nothing to
assert against. This writes a tiny stand-in corpus in the same layout the acts sync
already understands, which means a fresh clone can reach a populated review workspace
with no private data.

Why generated rather than committed as files: the PDFs have to carry a real text layer.
``pypdf``'s ``add_blank_page`` -- what the unit tests use -- produces pages pdf.js draws
blank, and the portal deliberately reports a blank render as a failure, so blank pages
cannot exercise the PDF pane. Emitting the PDFs here keeps the fixtures reviewable as
source instead of as opaque binaries, and keeps them byte-identical on every machine.

Layout written under ``--dest`` (the ``acts_repo`` layout from backend.sync_acts):

    Acts/<name>.pdf       source PDF, named by each JSON's metadata.filename
    output/<name>.json    structure JSON; its stem becomes the document name
    smoke_targets.json    manifest consumed by apps/web/scripts/visual_smoke.mjs

Usage:
    python tools/fixture_corpus.py [--dest data/fixtures/acts]
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "data" / "fixtures" / "acts"

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
LEFT_MARGIN, TOP_BASELINE, LINE_HEIGHT = 64, 720, 18


def _escape(text: str) -> str:
    """Escape the three characters that are special inside a PDF literal string."""
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(lines: List[str]) -> bytes:
    """One page's text as a PDF content stream, 12pt Helvetica, top-down."""
    parts = ["BT", "/F1 12 Tf", f"1 0 0 1 {LEFT_MARGIN} {TOP_BASELINE} Tm", f"{LINE_HEIGHT} TL"]
    for line in lines:
        parts.append(f"({_escape(line)}) Tj")
        parts.append("T*")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1", "replace")


def build_pdf(pages: List[List[str]]) -> bytes:
    """A minimal single-font PDF with a genuine text layer, one entry per page.

    Hand-rolled rather than taken from a library because no PDF *writer* is a
    dependency of this repo -- pypdf, pypdfium2 and pdfplumber are all readers here,
    and pypdf can only add blank pages. Adding reportlab just for fixtures would put a
    new dependency in the install path of everyone who never runs this.
    """
    if not pages:
        raise ValueError("a PDF needs at least one page")

    # Object numbering: 1 catalog, 2 page tree, 3 font, then (page, content) per page.
    page_ids = [4 + 2 * index for index in range(len(pages))]
    objects: Dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            "<< /Type /Pages /Kids ["
            + " ".join(f"{pid} 0 R" for pid in page_ids)
            + f"] /Count {len(pages)} >>"
        ).encode("ascii"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    for index, lines in enumerate(pages):
        page_id = page_ids[index]
        stream = _content_stream(lines)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>"
        ).encode("ascii")
        objects[page_id + 1] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: Dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode("ascii") + objects[number] + b"\nendobj\n"

    # The xref table must be byte-exact: every entry is a fixed 20-byte record, and
    # startxref is the absolute offset of the table itself.
    xref_offset = len(out)
    highest = max(objects)
    out += f"xref\n0 {highest + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for number in range(1, highest + 1):
        if number in offsets:
            out += f"{offsets[number]:010d} 00000 n \n".encode("ascii")
        else:
            out += b"0000000000 65535 f \n"
    out += (
        f"trailer\n<< /Size {highest + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)


def _section(code: str, heading: str, start: int, end: int, body: List[str]) -> Dict:
    plain = " ".join(body)
    paragraphs = "".join(f"<p>{line}</p>" for line in body)
    return {
        "code": code,
        "heading": heading,
        "start_page": start,
        "end_page": end,
        "html": f"<h3>{code}. {heading}</h3>{paragraphs}",
        "plain_text": f"{code}. {heading} {plain}",
        "footnotes": [
            {
                "marker": "1",
                "page": start,
                "text": f"Inserted by the fixture corpus for section {code}.",
                "html": f"<span>Inserted by the fixture corpus for section {code}.</span>",
            }
        ],
    }


def _fixtures() -> List[Dict]:
    """Three acts, each with several pages and leaves, and one deliberate multi-page leaf.

    Section text is long enough that the review page's 'thin_ui_text' assertion (40
    characters of rendered UI text) is met from the parsed HTML pane alone.
    """
    return [
        {
            "name": "Fixture Finance Act 2024",
            "smoke_page": 3,
            "chapters": [
                {
                    "code": "I",
                    "heading": "Preliminary",
                    "sections": [
                        _section("1", "Short title and commencement", 1, 1, [
                            "This Act may be called the Fixture Finance Act, 2024.",
                            "It shall come into force on the first day of July, 2024.",
                        ]),
                        _section("2", "Definitions", 2, 3, [
                            "In this Act, unless there is anything repugnant in the subject or context,",
                            "'assessment year' means the period of twelve months beginning on the first",
                            "day of July next following the income year.",
                            "'fixture' means a specimen record created solely for automated testing.",
                        ]),
                    ],
                },
                {
                    "code": "II",
                    "heading": "Charge of tax",
                    "sections": [
                        _section("3", "Rates of tax", 4, 4, [
                            "Subject to the provisions of this Act, tax shall be charged at the rates",
                            "specified in the First Schedule for each assessment year.",
                        ]),
                    ],
                },
            ],
        },
        {
            "name": "Fixture Sales Tax Act 1990",
            "smoke_page": 2,
            "chapters": [
                {
                    "code": "I",
                    "heading": "Scope and payment",
                    "sections": [
                        _section("3", "Scope of tax", 1, 2, [
                            "There shall be charged, levied and paid a tax known as sales tax at the",
                            "rate of eighteen per cent of the value of taxable supplies made by a",
                            "registered person in the course of any taxable activity carried on by him.",
                        ]),
                        _section("7", "Determination of tax liability", 3, 3, [
                            "For the purpose of determining his tax liability in respect of a tax period,",
                            "a registered person shall be entitled to deduct input tax paid or payable.",
                        ]),
                    ],
                },
            ],
        },
        {
            "name": "Fixture Customs Act 1969",
            "smoke_page": 3,
            "chapters": [
                {
                    "code": "I",
                    "heading": "Levy of customs duties",
                    "sections": [
                        _section("18", "Goods dutiable", 1, 1, [
                            "Customs duties shall be levied at such rates as are prescribed in the",
                            "First Schedule or under any other law for the time being in force.",
                        ]),
                        _section("25", "Value of imported goods", 2, 3, [
                            "The customs value of imported goods shall be the transaction value,",
                            "that is the price actually paid or payable for the goods when sold for",
                            "export to Pakistan, adjusted in accordance with the provisions of this section.",
                        ]),
                    ],
                },
            ],
        },
    ]


def _pdf_pages_for(fixture: Dict, total_pages: int) -> List[List[str]]:
    """Render each PDF page from the leaves that declare it, so both panes agree."""
    leaves = [
        section
        for chapter in fixture["chapters"]
        for section in chapter["sections"]
    ]
    pages: List[List[str]] = []
    for number in range(1, total_pages + 1):
        lines = [fixture["name"].upper(), ""]
        for section in leaves:
            if section["start_page"] <= number <= section["end_page"]:
                lines.append(f"{section['code']}. {section['heading']}")
                lines.append("")
                lines.extend(
                    line
                    for line in section["html"]
                    .replace("</p><p>", "\n")
                    .split("\n")
                    if not line.startswith("<h3>")
                )
                lines.append("")
        lines.append(f"Page {number} of {total_pages}")
        # Strip any residual markup so the text layer reads as prose.
        pages.append([_strip_tags(line) for line in lines])
    return pages


def _strip_tags(text: str) -> str:
    out, depth = [], 0
    for char in text:
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(char)
    return "".join(out).strip()


def build(dest: Path) -> Dict:
    acts_dir = dest / "Acts"
    output_dir = dest / "output"
    if dest.exists():
        shutil.rmtree(dest)
    acts_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    targets = []
    for fixture in _fixtures():
        total_pages = max(
            section["end_page"]
            for chapter in fixture["chapters"]
            for section in chapter["sections"]
        )
        pdf_name = f"{fixture['name']}.pdf"
        (acts_dir / pdf_name).write_bytes(
            build_pdf(_pdf_pages_for(fixture, total_pages))
        )
        document = {
            "metadata": {
                "filename": pdf_name,
                "total_pages": total_pages,
                "title": fixture["name"],
            },
            "chapters": fixture["chapters"],
            "schedules": [],
        }
        # The JSON stem becomes the document name, which is what the smoke targets match.
        (output_dir / f"{fixture['name']}.json").write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )
        targets.append({"nameIncludes": fixture["name"], "page": fixture["smoke_page"]})

    manifest = {
        "generator": "tools/fixture_corpus.py",
        "note": "Regenerate with `make seed-fixtures`. Not a substitute for the real corpus.",
        "targets": targets,
    }
    (dest / "smoke_targets.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    args = parser.parse_args()

    manifest = build(args.dest.resolve())
    print(f"Wrote {len(manifest['targets'])} fixture act(s) to {args.dest}")
    for target in manifest["targets"]:
        print(f"  {target['nameIncludes']} (smoke page {target['page']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""What a document IS, measured from its text layer alone.

This is the input to :mod:`legal_ingest.families`, and it exists because the
pipeline used to answer "what kind of document is this?" with "whichever
directory it was in".  Three lanes, three parsing behaviours, chosen by folder.
Measured over the 183-document FBR inventory that is wrong on four axes at once:

  * The Acts lane holds 25 *amending* instruments -- Finance Acts and the
    "(Amendment) Act" family -- whose leaves are directives quoting a DIFFERENT
    law.  Parsed as consolidated statutes they emit the Gazette masthead as a
    chapter (``The Tax Laws (Amendment) Act, 2024``: chapter ``code="PART I"``,
    ``heading="Acts, Ordinances, President's Orders and Regulations"``).
  * The Ordinance lane routes 9 flat, TOC-less ICT (Tax on Services) Ordinance
    editions to a pipeline with no body-driven fallback.
  * Container shape varies WITHIN a lane (``CPD`` for the Income Tax Ordinance,
    ``C`` for Customs, flat for ICT) and is stable ACROSS editions (Customs holds
    CH~44/PT=14 over twenty editions, 2007-2025).
  * It varies across ERAS within one group: the Income Tax Ordinance's editions
    from 30.06.2024 measure 514 chapter lines against 42 for every earlier one,
    because the publisher re-typeset it.

Deliberately text-only.  Every field below is a regex over ``pdftotext -layout``
lines; no page geometry, no ``pdfplumber``, no ``calibrate()``.  That is what
keeps a signature cheap enough (~50ms typical, 2.6s for the 952-page Finance Act
2022) to take in production as well as in discovery, and what keeps this module
importable without the heavy parse stack.

Every regex that already exists is imported, not rewritten -- the container set
from :mod:`grammar`, the contents-row set from :mod:`calibrate`.  The two that
are local are local for a stated reason, given at each.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .calibrate import TOC_DOT_LEADER_RE, TOC_LEADER_RE, TOC_ROW_RE
from .grammar import CHAPTER_RE, CODE, DIVISION_RE, PART_RE, SCHEDULE_RE, TABLE_RE

#: A body leaf opening its own line: "12.", "12A.", "[12A.", "221-A.".  Built from
#: ``grammar.CODE`` so the numbering grammar stays in ONE place -- the Customs
#: Rules 2001 runs past a thousand (1110) and the Acts carry four suffix letters
#: (3AAA), both of which CODE already knows and a hand-rolled \d{1,3} would not.
#: Contents rows match this too; that is fine, since the only predicate reading
#: it asks whether the document has leaves at all.
LEAF_LINE_RE = re.compile(rf"^\s*\[?\s*({CODE})\s*\.\s")

#: Amending language, measured over the WHOLE text with no zone model.
#:
#: It cannot reuse ``discover.amending_density``: that takes body-zone LineRefs,
#: because its ``_AMENDING_RE`` includes "for the words|figures|expression",
#: which is what a CONSOLIDATED act's own footnotes say ("substituted for the
#: words ... by the Finance Act, 2019").  Counting those over full text inverts
#: the test -- discover.py's docstring records footnote-zone density running 270
#: on Finance Act 2013 against 0.09 body-zone on Customs.
#:
#: This pattern keeps only the DIRECTIVE forms, which a footnote never uses (a
#: footnote says "Substituted by", an enactment says "shall be substituted"), so
#: it is safe with no zones.  Measured over all 144 text-bearing documents it
#: separates the populations by more than 20x: consolidated 0.1-0.2, amending
#: 4.6-23.9.
#: ``\s+`` between every word, not a literal space: ``-layout`` wraps at the
#: printed line, and the Anti-Terrorism (Third Amendment) Act 2020 -- a
#: one-page instrument that is nothing BUT an amendment -- breaks its only
#: directive across the wrap ("...the new section shall be\ninserted,
#: namely:-"). With a literal space it measured density 0.00 and fell out of
#: every family.
AMENDING_RE = re.compile(
    r"shall\s+be\s+(?:substituted|inserted|omitted|added|re-?numbered)"
    r"|\b(?:in|of)\s+the\s+said\s+(?:Act|Ordinance|Rules|Notification)\b",
    re.IGNORECASE)

#: A numbered clause of an amending instrument naming the law it amends:
#: "4. Amendments of the Customs Act, 1969 (IV of 1969)".
#:
#: Not decoration -- required.  Finance Act 2022 (952 pages) measures amending
#: density 1.2, UNDER the 2.0 gate, because it reproduces a 175-entry tariff
#: schedule that dilutes it.  It carries 3 directive headings.  Density alone
#: files the largest amending instrument in the corpus as consolidated.
DIRECTIVE_HEADING_RE = re.compile(
    r"^\s*\d{1,3}\.\s*Amendments?\s+(?:of|in|to)\s+the\s+.{3,80}?"
    r"(?:Act|Ordinance|Rules)\b",
    re.IGNORECASE | re.MULTILINE)



#: The Gazette masthead's own section line. A publication section, not a
#: structural container -- and the line that becomes a chapter today.
MASTHEAD_RE = re.compile(r"Acts,\s*Ordinances,\s*President", re.IGNORECASE)

_SRO_RE = re.compile(r"S\.?\s?R\.?\s?O\.?\s*\d")
_FORM_RE = re.compile(r"^\s*(?:FORM|ANNEX(?:URE)?|APPENDIX)\b[-\s]*[A-Z0-9]", re.IGNORECASE)
_FOOTNOTE_BRACKET_RE = re.compile(r"\d{1,4}\[")
_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LEXICON_RE = {
    "section": re.compile(r"sub-?section", re.IGNORECASE),
    "rule": re.compile(r"sub-?rule", re.IGNORECASE),
    "regulation": re.compile(r"sub-?regulation", re.IGNORECASE),
    "article": re.compile(r"\barticles?\s+\d", re.IGNORECASE),
}

#: Below this, the text layer is absent or unusable and nothing else measured on
#: the document means anything.  The corpus splits cleanly: 144 documents sit
#: above 300 characters per page, 39 sit below, and the nearest to the line is
#: Finance Act 2025 at 70 -- which the inventory calls "Mixed (text+image)" and
#: which is, measured, a scan.
TEXT_LAYER_FLOOR = 300

#: A container kind counted fewer times than this is noise, not structure: every
#: gazette instrument prints "PART I" once in its masthead.
CONTAINER_FLOOR = 3

PDF_MAGIC = b"%PDF"


@dataclass(frozen=True)
class Signature:
    """One document's measured structure. All fields scalar, so ``asdict()``
    serialises with no custom encoder and a rerun diffs line by line."""

    # -- identity, relative to the LANE's source root, so the first segment is
    #    the document group. That holds for 183/183 inventory rows, three-deep
    #    Recruitment Rules included: the cadre folder is a SUB-group, and
    #    ``Document Group`` there is still the first segment.
    #
    #    The lane is not a field. It is where the file was filed, which is the
    #    fact this whole module exists to stop treating as structure -- the
    #    Acts folder holds two families and the Ordinance folder holds four.
    #    The census carries it alongside, as provenance.
    path: str
    group: str
    extension: str            # "" for the 19 extensionless real PDFs

    # -- text layer
    pages: int
    chars_per_page: int
    script: str               # "latin" | "arabic"
    arabic_chars: int

    # -- front matter and contents
    toc_rows: int
    toc_dot_leaders: int
    toc_other_leaders: int    # hyphen/underscore runs (Income Tax Rules 2002)
    gazette_masthead: bool

    # -- containers
    chapter_lines: int
    part_lines: int
    division_lines: int
    table_lines: int
    schedule_lines: int
    container_order: str      # "" | "C" | "CP" | "CPD" | "P" ... first-seen order

    # -- leaves
    leaf_lines: int
    leaf_lexicon: str         # section | rule | regulation | article | unknown
    max_leaf_code: int

    # -- instrument kind
    amending_density: float
    directive_headings: int
    sro_mentions: int
    form_lines: int

    # -- typography
    footnote_brackets: int
    producer: str
    #: DIAGNOSTIC ONLY. It is the direct explanation for the Income Tax Ordinance
    #: 30.06.2024 typesetting break, and explaining drift is the report's job.
    #: NO FAMILY PREDICATE MAY READ IT -- a predicate on the producer string is a
    #: filename special-case wearing a different hat.

    def as_dict(self) -> dict:
        return asdict(self)


def is_pdf(path: Path) -> bool:
    """Magic-byte test. Nineteen corpus sources have no ``.pdf`` extension."""
    try:
        with Path(path).open("rb") as handle:
            return handle.read(len(PDF_MAGIC)) == PDF_MAGIC
    except OSError:
        return False


def _pdfinfo(path: Path) -> tuple[int, str]:
    try:
        out = subprocess.run(["pdfinfo", str(path)], capture_output=True,
                             timeout=60).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return 0, ""
    pages, producer = 0, ""
    for line in out.splitlines():
        key, _, value = line.partition(":")
        if key == "Pages":
            pages = int(value.strip() or 0)
        elif key == "Producer":
            producer = value.strip()
    return pages, producer


def extract_text(path: Path) -> str:
    """The document's text layer, laid out. Empty when there is none.

    ``-layout`` matters: contents rows are recognised by leader runs and trailing
    folios, both of which the default reading-order mode destroys.
    """
    # ponytail: re-extracts text the parse stage will read again through
    # pdfplumber. Measured 9s for the whole 183-document corpus, so the
    # duplication is cheaper than threading a text handle through both stacks.
    # Share the extraction when a single conversion's wall time starts to matter.
    try:
        return subprocess.run(["pdftotext", "-q", "-layout", str(path), "-"],
                              capture_output=True, timeout=300
                              ).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return ""


def _container_order(first_seen: dict[str, int]) -> str:
    """Present containers, in the order the document first prints them."""
    return "".join(letter for letter, _ in sorted(first_seen.items(), key=lambda kv: kv[1]))


def measure(path, root=None) -> Signature:
    """Measure one document. ``root`` scopes ``path`` for the identity fields."""
    path = Path(path)
    rel = path.relative_to(root).as_posix() if root else path.name
    parts = rel.split("/")

    ext = path.suffix.lower()

    if ext in (".doc", ".docx") or not is_pdf(path):
        pages, producer, text = 0, "", ""
    else:
        pages, producer = _pdfinfo(path)
        text = extract_text(path)

    chars = len(text)
    lines = text.split("\n")
    arabic = len(_ARABIC_RE.findall(text))

    counts = {"C": 0, "P": 0, "D": 0}
    first_seen: dict[str, int] = {}
    schedule_lines = table_lines = leaf_lines = 0
    toc_rows = toc_dots = toc_other = form_lines = 0
    max_leaf_code = 0

    for i, line in enumerate(lines):
        for letter, pattern in (("C", CHAPTER_RE), ("P", PART_RE), ("D", DIVISION_RE)):
            if pattern.match(line):
                counts[letter] += 1
                first_seen.setdefault(letter, i)
        if TABLE_RE.match(line):
            table_lines += 1
        if SCHEDULE_RE.match(line):
            schedule_lines += 1
        if _FORM_RE.match(line):
            form_lines += 1
        if TOC_ROW_RE.match(line):
            toc_rows += 1
        if TOC_DOT_LEADER_RE.search(line):
            toc_dots += 1
        elif TOC_LEADER_RE.search(line):
            toc_other += 1
        leaf = LEAF_LINE_RE.match(line)
        if leaf:
            leaf_lines += 1
            digits = re.match(r"\d+", leaf.group(1))
            if digits:
                max_leaf_code = max(max_leaf_code, int(digits.group()))

    lexicon_hits = {name: len(rx.findall(text)) for name, rx in _LEXICON_RE.items()}
    best = max(lexicon_hits, key=lambda k: lexicon_hits[k])

    # A container kind under the floor is masthead noise, not structure.
    first_seen = {k: v for k, v in first_seen.items() if counts[k] >= CONTAINER_FLOOR}

    return Signature(
        path=rel,
        group=parts[0] if len(parts) > 1 else "",
        extension=ext,
        pages=pages,
        chars_per_page=round(chars / pages) if pages else 0,
        # Any Arabic at all. Measured over all 183 documents this is exact: the
        # only four files carrying a single Arabic codepoint are the four the
        # inventory marks Urdu, and their shares run 0.028 to 0.518 -- so a
        # share threshold would have to be under 3% to catch the Asset
        # Declaration Rules, whose body font extracts as Latin noise and leaves
        # only its cover in real Urdu. A count of zero is the cleaner cut.
        script="arabic" if arabic else "latin",
        arabic_chars=arabic,
        toc_rows=toc_rows,
        toc_dot_leaders=toc_dots,
        toc_other_leaders=toc_other,
        gazette_masthead=bool(MASTHEAD_RE.search(text)),
        chapter_lines=counts["C"],
        part_lines=counts["P"],
        division_lines=counts["D"],
        table_lines=table_lines,
        schedule_lines=schedule_lines,
        container_order=_container_order(first_seen),
        leaf_lines=leaf_lines,
        leaf_lexicon=best if lexicon_hits[best] else "unknown",
        max_leaf_code=max_leaf_code,
        amending_density=round(10000.0 * len(AMENDING_RE.findall(text)) / chars, 2) if chars else 0.0,
        directive_headings=len(DIRECTIVE_HEADING_RE.findall(text)),
        sro_mentions=len(_SRO_RE.findall(text)),
        form_lines=form_lines,
        footnote_brackets=len(_FOOTNOTE_BRACKET_RE.findall(text)),
        producer=producer,
    )


def _demo() -> None:
    # The two local regexes are the ones a corpus change can invalidate, so they
    # are pinned against the exact lines that forced them.
    assert AMENDING_RE.search("the new section shall be inserted, namely:-")
    assert AMENDING_RE.search("In the said Act, in section 2,")
    # wrapped by -layout at the printed line -- Anti-Terrorism (3rd Amdt) 2020
    assert AMENDING_RE.search("the new section shall be\ninserted, namely:-")
    # ...and must NOT fire on a consolidated act's own amendment footnote, which
    # is what forced this pattern to be narrower than discover._AMENDING_RE.
    assert not AMENDING_RE.search(
        'Substituted for the words "sales tax" by the Finance Act, 2019')

    assert DIRECTIVE_HEADING_RE.search("4. Amendments of the Customs Act, 1969 (IV of 1969)")
    assert DIRECTIVE_HEADING_RE.search("2. Amendments in the Sales Tax Act, 1990")
    assert not DIRECTIVE_HEADING_RE.search("2. Definitions.- In this Act,")

    # CODE, not \d{1,3}: Customs Rules 2001 runs to rule 1110 and the Acts carry
    # four suffix letters. Both were silent renumberings before grammar.py.
    assert LEAF_LINE_RE.match("1110. Application.- ")
    assert LEAF_LINE_RE.match("3AAA. Levy and collection of tax. ")
    assert LEAF_LINE_RE.match("  221-A. Recovery. ")
    assert not LEAF_LINE_RE.match("(1) This Act may be called")

    assert MASTHEAD_RE.search("Acts, Ordinances, President's Orders and Regulations")

    # first-print order, and the masthead's lone "PART I" stays under the floor
    assert _container_order({"C": 10, "P": 40, "D": 55}) == "CPD"
    assert _container_order({"P": 4, "C": 9}) == "PC"
    assert _container_order({}) == ""

    assert TEXT_LAYER_FLOOR == 300 and CONTAINER_FLOOR == 3
    assert _ARABIC_RE.search("ااہظرِ دربتسداری") and not _ARABIC_RE.search("Short title.")
    print("signature self-check passed")


if __name__ == "__main__":
    _demo()

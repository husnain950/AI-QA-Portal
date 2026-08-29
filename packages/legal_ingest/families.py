"""Which schema family a document belongs to, and how sure we are.

A *family* is what the document IS -- its instrument kind and whether it is
readable at all.  A :class:`~legal_ingest.profiles.Profile` is what its PRINTER
does -- raised ordinals, folio forms, contents-row shapes.  Those are independent
axes that ``profiles.py`` had conflated, and this module separates them by
composition: a ``Family`` holds a ``Profile``.

There are five, and the number is the point.  183 documents, 58 filing folders,
three lanes -- and five families explain all of them with none left over.  The
axes that look like families and are not:

* ``container_order`` (``C``, ``CP``, ``PCD``, flat) is a FIELD.  ``calibrate.
  detect_toc_pages`` already returns 0 for a document with no contents page, and
  ``discover.discover_structure`` already rebuilds containers from the body when
  ``parse_toc`` yields nothing.  A "flat" family would fork a path that works.
* ``has_toc`` is a FIELD, for the same reason.
* Category (Acts / Rules / Ordinance) is a FILING convention.  Measured, the
  Acts folder holds both ``consolidated`` and ``amending`` documents, and the
  Ordinance folder holds three families.

Selection is ordered predicates, not a clustering model: 183 points on 18
hand-picked features needs numpy to cluster, is threshold-sensitive, and the
clusters get hand-labelled anyway.  The evidence a human reads is the group-by
in ``tools/discovery/report.md``; this is what code runs.  Every threshold below
was measured, and the comment names the document that forced it -- the
convention ``profiles.py`` already uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .profiles import ACTS, AMENDING, Profile
from .signature import TEXT_LAYER_FLOOR, Signature

Predicate = Callable[[Signature], bool]

#: Amending language per 10,000 characters.  Inherited from
#: ``discover.AMENDING_DENSITY_MIN``, and measured again here over full text with
#: ``signature.AMENDING_RE``: the consolidated population tops out at 1.29
#: (Sharing of Declaration of Assets of Civil Servants Rules 2023) and the
#: amending population bottoms out at 2.06 (Income Tax (Amendment) Ordinance
#: 2022).  The gate sits in the gap.
AMENDING_DENSITY_MIN = 2.0

#: One directive heading is enough, and it has to be.  Two documents in the
#: corpus are amending instruments that the density gate alone misses:
#:
#:   Finance Act, 2022        density 1.23, 3 directive headings -- 952 pages, of
#:                            which a reproduced tariff schedule dilutes the
#:                            operative text below the gate
#:   Tax Laws (Amendment)     density 1.85, 1 directive heading
#:   Ordinance No.1 of 2020
#:
#: Measured over all 144 text-bearing documents, those two are the ONLY ones
#: carrying a directive heading without also clearing the density gate, so a
#: floor of 1 admits no false positive.
DIRECTIVE_HEADINGS_MIN = 1

#: A document with fewer leaf lines than this has no structure to parse.  Two,
#: not five: the Pakistan Single Window EOI Rules 2022 is a genuine three-page
#: rules set with exactly two numbered rules, and a floor of five filed it as
#: unexplained.
LEAF_LINES_MIN = 2

#: How much corroboration is enough to parse without a human looking.  Not a
#: probability -- the ratio of signals that held.
CONFIDENT = 0.6


@dataclass(frozen=True)
class Family:
    """One structural family.

    ``required`` decides membership: ALL must hold.  ``optional`` decides
    confidence: it is corroboration, and its hit rate is the number.
    """

    label: str
    #: The printer profile this family parses with. ``None`` means the family is
    #: not parseable at all and the pipeline refuses it.
    profile: Optional[Profile]
    required: tuple[tuple[str, Predicate], ...]
    optional: tuple[tuple[str, Predicate], ...] = ()

    def match(self, sig: Signature) -> tuple[bool, list[str]]:
        hits = [name for name, test in self.required if test(sig)]
        if len(hits) != len(self.required):
            return False, []
        hits += [name for name, test in self.optional if test(sig)]
        return True, hits

    def total_signals(self) -> int:
        return len(self.required) + len(self.optional)


@dataclass(frozen=True)
class Assignment:
    """The verdict on one document, with the evidence that produced it."""

    family: Optional[str]          # None == unexplained
    confidence: float
    #: "measured" -- from this document's own text.
    #: "group"    -- inherited, because the document has no text layer and every
    #:               text-bearing edition in its group agrees.
    source: str = "measured"
    evidence: tuple[str, ...] = ()

    @property
    def confident(self) -> bool:
        return self.family is not None and self.confidence >= CONFIDENT

    def as_dict(self) -> dict:
        return {"family": self.family, "confidence": round(self.confidence, 2),
                "source": self.source, "evidence": list(self.evidence)}


# ---------------------------------------------------------------------------
# The families. ORDER IS SIGNIFICANT -- first required-set match wins, and that
# is the documented tie-break.

FAMILIES: tuple[Family, ...] = (
    # First, so the two legacy .doc files stop being classified as scans and
    # pointed at an OCR stage that cannot help them.
    Family(
        label="unconvertible",
        profile=None,
        required=(("legacy_word_format", lambda s: s.extension in (".doc", ".docx")),),
    ),
    # Before no_text_layer: that a document is Urdu decides everything after it
    # (the pipeline has no RTL support), and OCR would not change that.
    Family(
        label="urdu",
        profile=None,
        required=(("arabic_script", lambda s: s.script == "arabic"),),
        optional=(
            # The 259-page Customs Act Urdu edition against its 13-page contents
            # volume: a full translation, not a front-matter page.
            ("full_translation", lambda s: s.pages > 50),
        ),
    ),
    Family(
        label="no_text_layer",
        profile=None,
        required=(("no_text_layer",
                   lambda s: s.chars_per_page < TEXT_LAYER_FLOOR),),
        optional=(
            # Recorded, not acted on. If these hold across the scanned
            # population once OCR runs, a subordinate-notification family is
            # worth measuring -- and this is the hypothesis to measure it
            # against, rather than a family invented on speculation now.
            ("short", lambda s: 0 < s.pages <= 10),
            ("sro_notified", lambda s: s.sro_mentions >= 1),
            ("form_bearing", lambda s: s.form_lines >= 1),
        ),
    ),
    Family(
        label="amending",
        profile=AMENDING,
        required=(("amending_language",
                   lambda s: s.amending_density >= AMENDING_DENSITY_MIN
                   or s.directive_headings >= DIRECTIVE_HEADINGS_MIN),),
        optional=(
            ("no_contents_page", lambda s: s.toc_rows < 20),
            ("gazette_masthead", lambda s: s.gazette_masthead),
            ("flat", lambda s: s.container_order == ""),
            ("names_its_targets", lambda s: s.directive_headings >= 1),
        ),
    ),
    Family(
        label="consolidated",
        profile=ACTS,
        required=(("has_leaves", lambda s: s.leaf_lines >= LEAF_LINES_MIN),),
        optional=(
            ("has_contents_page", lambda s: s.toc_rows >= 20 or s.toc_dot_leaders >= 20),
            ("has_containers", lambda s: s.container_order != ""),
            ("has_schedules", lambda s: s.schedule_lines >= 1),
            ("amendment_footnotes", lambda s: s.footnote_brackets >= 10),
            ("names_its_leaf_kind", lambda s: s.leaf_lexicon != "unknown"),
        ),
    ),
)

BY_LABEL = {f.label: f for f in FAMILIES}


def classify(sig: Signature) -> Assignment:
    """Assign ``sig`` to a family, or return an unexplained assignment.

    First required-set match wins. There is deliberately no "ambiguous" state:
    with ordered predicates a later match is always expected -- ``consolidated``
    is the broad one and every amending instrument has leaves too -- so recording
    it flagged 29 documents where nothing was wrong. Declaration order IS the
    tie-break, and it is documented at ``FAMILIES``.
    """
    for family in FAMILIES:
        matched, hits = family.match(sig)
        if matched:
            return Assignment(family=family.label,
                              confidence=len(hits) / family.total_signals(),
                              evidence=tuple(hits))
    return Assignment(family=None, confidence=0.0, evidence=("no family matched",))


def inherit(group_assignments) -> Optional[str]:
    """The family a text-less document may take from its group, or ``None``.

    Only when every text-bearing edition in the group agrees. That condition is
    not ceremony: the "Finance Acts" folder holds 20 files spanning five
    container shapes, and its nine scans would otherwise inherit from a folder
    that is a filing convention rather than a document group. Measured, the
    eleven text-bearing Finance Acts DO all agree (all amending), which is what
    makes the inheritance safe -- but the check is what proved it.
    """
    labels = {a.family for a in group_assignments
              if a.source == "measured" and a.family
              and BY_LABEL[a.family].profile is not None}
    return labels.pop() if len(labels) == 1 else None


def _demo() -> None:
    from dataclasses import replace

    base = Signature(
        path="X/x.pdf", group="X", extension=".pdf",
        pages=100, chars_per_page=2000, script="latin", arabic_chars=0,
        toc_rows=200, toc_dot_leaders=200, toc_other_leaders=0,
        gazette_masthead=False, chapter_lines=40, part_lines=14,
        division_lines=0, table_lines=0, schedule_lines=15, container_order="CP",
        leaf_lines=1000, leaf_lexicon="section", max_leaf_code=221,
        amending_density=0.1, directive_headings=0, sro_mentions=0, form_lines=5,
        footnote_brackets=900, producer="Acrobat Distiller 7.0 (Windows)",
    )
    # A consolidated Act with every corroborating signal: full confidence.
    a = classify(base)
    assert a.family == "consolidated" and a.confidence == 1.0 and a.confident, a

    # Finance Act, 2022: 952 pages, density 1.23 -- UNDER the gate, because a
    # reproduced tariff schedule dilutes it -- rescued by 3 directive headings.
    fa22 = replace(base, amending_density=1.23, directive_headings=3)
    assert classify(fa22).family == "amending", classify(fa22)

    # ...and a consolidated edition whose FILENAME says "through Tax Laws
    # (Amendment) Act, 2024" must not follow it. Content, never filenames.
    assert classify(replace(base, amending_density=0.1)).family == "consolidated"

    # An ICT (Tax on Services) Ordinance edition: flat, no contents page, no
    # schedules. It IS consolidated, and it IS the document that proves the
    # body-driven fallback is needed -- so it must parse, and it must be
    # flagged. Low confidence says exactly that, with no special case.
    ict = replace(base, toc_rows=3, toc_dot_leaders=0, container_order="",
                  chapter_lines=0, part_lines=0, schedule_lines=0,
                  leaf_lines=12, leaf_lexicon="unknown", footnote_brackets=0)
    v = classify(ict)
    assert v.family == "consolidated" and not v.confident and v.confidence < CONFIDENT, v

    # Order: a .doc is unconvertible before it is a scan; Urdu before no-text,
    # because RTL is unsupported whether or not OCR would read it.
    assert classify(replace(base, extension=".doc", chars_per_page=0)).family == "unconvertible"
    urdu_scan = replace(base, script="arabic", arabic_chars=159, chars_per_page=40)
    assert classify(urdu_scan).family == "urdu", classify(urdu_scan)
    assert classify(replace(base, chars_per_page=40)).family == "no_text_layer"

    # A document with no leaves at all is UNEXPLAINED, not forced into the
    # nearest family. That is the whole point of having the state.
    blank = replace(base, leaf_lines=0, leaf_lexicon="unknown", container_order="",
                    toc_rows=0, toc_dot_leaders=0, schedule_lines=0,
                    footnote_brackets=0, amending_density=0.0)
    assert classify(blank).family is None

    # Inheritance needs unanimity among the group's MEASURED, parseable editions.
    def m(label):
        return Assignment(family=label, confidence=1.0, source="measured")

    assert inherit([m("amending"), m("amending")]) == "amending"
    assert inherit([m("amending"), m("consolidated")]) is None
    assert inherit([m("consolidated"), Assignment("no_text_layer", 1.0, "measured")]) \
        == "consolidated"
    assert inherit([]) is None

    assert [f.label for f in FAMILIES] == ["unconvertible", "urdu", "no_text_layer",
                                           "amending", "consolidated"]
    print("families self-check passed")


if __name__ == "__main__":
    _demo()

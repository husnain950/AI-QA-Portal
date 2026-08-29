"""What differs between the documents this pipeline reads.

`fbr_ingest` (the Ordinance) is a separate pipeline. Within *this* one, the Acts and
the Rules corpora were for a while two verbatim forks of the same 11,500 lines. Nine
of the thirteen modules were byte-identical; the rest differed in the ways recorded
below.

**They are not, however, "the same family of document", which is what this docstring
used to claim.** Measured over the 183-document inventory, the Acts folder holds two
structurally unrelated instrument kinds: 117 CONSOLIDATED statutes (CHAPTER / PART /
numbered leaf / footnote block) and 25 AMENDING ones -- the Finance Acts and the
"(Amendment) Act" family -- whose leaves are directives quoting a DIFFERENT law, and
which print no containers of their own beyond the gazette's masthead. A corpus label
never separated those; :mod:`legal_ingest.families` does.

A `Profile` is what a document's PRINTER does. A `Family` is what the document IS.
They are independent axes and this file used to conflate them; `families.py` holds
the second and composes this one into it.

Most of that divergence was not a difference of corpus at all, but a fix one fork got
and the other did not: a TOC-side schedule anchor whose comment said it was "the same
rule, applied on the TOC side, where it had never been added"; a heading terminator that
read one hyphen where the printer set two; an orphan check whose docstring admitted the
Acts version "always said no". Those are adopted for both corpora unconditionally --
gating them per-corpus would be choosing to keep a known bug.

What genuinely varies is what the two printers actually do differently, and that is what
a `Profile` carries. Every field below was measured against real PDFs, and the comment
names the document that forced it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    #: registry label -- matches `backend.services.corpus_registry`.
    label: str

    #: `metadata.instrument_kind` in the output. None omits the key, which is what the
    #: Acts corpus has always done; adding it there would change every Acts document.
    instrument_kind: str | None = None

    # -- raised ordinal suffixes ("24th", "1st") ---------------------------------
    #: How far a superscript suffix may sit AFTER its number, and how far above the
    #: line, before it stops being read as part of it. The lower gap bound is fixed
    #: at -1.0 for every corpus (a negative gap is overlap). The tighter Acts pair was
    #: measured on the Acts corpus; Sales Tax Special Procedures 05.03.2015 raises
    #: its suffixes to dtop 3.34-5.69 and one to gap 2.22, putting 19 ordinals on 12
    #: pages outside them. Widening for the Acts too would start merging tokens no
    #: Acts document has ever been read as merged, so it stays per corpus.
    ordinal_gap_max: float = 1.0
    ordinal_dtop_max: float = 2.5

    #: Recover a suffix that pdfplumber sorted onto a NEIGHBOURING line, by geometry
    #: rather than stream order. Only the Rules corpus raises them far enough to need
    #: it; on the Acts it would be a new way for a token to move.
    reattach_raised_ordinals: bool = False

    # -- printed page numbers (folios) -------------------------------------------
    #: The Acts print a lone centred integer. The Rules print three forms, two of
    #: which are not lone integers: "(104)" (Sales Tax Rules 2006) and a running
    #: title whose last token is the folio ("Income Tax Rules, 2002   9"). Reading
    #: only the bare form, Sales Tax Rules derived page offset 16 with 0% support --
    #: the real offset is 17 -- and every footnote ref on 224 pages is minted from it.
    #:
    #: Both stay off for the Acts, and the parenthesised form is why: a centred
    #: subsection marker in a footer band ("(2)") is indistinguishable from a
    #: parenthesised folio, and the Acts reader required `str.isdigit()` precisely
    #: so it could never confuse the two.
    folio_parenthesised: bool = False
    folio_running_title: bool = False

    # -- table of contents -------------------------------------------------------
    #: A SUB-CHAPTER row. Sales Tax Rules 2006 subdivides three of its chapters, a
    #: level the document tree does not model. The row is consumed rather than
    #: modelled, which stops it gluing onto the preceding heading.
    subchapter_rows: bool = False

    #: Contents rows set with hyphen or underscore leaders, not just dots
    #: (Income Tax Rules), and rows carrying no code at all.
    toc_hyphen_leaders: bool = False
    toc_codeless_rows: bool = False

    #: Require leader DENSITY as well as row count before extending the TOC tail.
    #: None keeps the row-count-only rule the Acts corpus was calibrated with.
    toc_tail_density_floor: float | None = None

    # -- instrument front matter -------------------------------------------------
    #: Extract the notifying S.R.O. into `metadata.notified_by`. Rules sets are
    #: notified by one; an Act is enacted, not notified.
    notifying_sro: bool = False

    # -- amending instruments ----------------------------------------------
    #: Reject a structural heading printed BEFORE the instrument's first clause.
    #:
    #: In an amending instrument the only container ahead of clause 1 is the
    #: gazette's own masthead -- "PART I / Acts, Ordinances, President's Orders
    #: and Regulations" -- which is a publication section, not a chapter of the
    #: Act. `discover._quoted_container` already rejects containers printed
    #: AFTER the first clause (they are quoted from the amended law) and its
    #: docstring names the masthead as the front-matter case it does NOT cover.
    #: This is that case. Left uncovered, `The Tax Laws (Amendment) Act, 2024`
    #: ships a chapter with `code="PART I"` and the masthead line as its
    #: heading, and its four real clauses hang beneath it.
    #:
    #: Off for the consolidated corpora, and Public Finance Management Act 2019
    #: is why it must stay off: it is a gazette reproducing an Act WITH ten
    #: chapters, and those chapters legitimately parent its sections.
    suppress_front_matter_containers: bool = False


ACTS = Profile(label="acts")

RULES = Profile(
    label="rules",
    instrument_kind="rules",
    ordinal_gap_max=2.5,
    ordinal_dtop_max=6.0,
    reattach_raised_ordinals=True,
    folio_parenthesised=True,
    folio_running_title=True,
    subchapter_rows=True,
    toc_hyphen_leaders=True,
    toc_codeless_rows=True,
    toc_tail_density_floor=0.20,
    notifying_sro=True,
)

#: An amending instrument -- a Finance Act, or any "(Amendment) Act/Ordinance".
#: It declares no structure of its own: a flat list of numbered directives, each
#: naming a law it changes and quoting the text it inserts. Selected by
#: :func:`legal_ingest.families.classify`, never by a corpus label -- the Acts
#: folder holds both kinds, and a filename cannot tell them apart (`Sales Tax
#: Act, 1990 as amended up to 07th May, 2024 through Tax Laws (Amendment) Act,
#: 2024` is consolidated, and measures amending density 0.1).
#:
#: The printer fields stay at the Acts settings: these documents are gazette
#: prints, and no typography difference has been measured against them. Only the
#: two structural fields move.
AMENDING = Profile(
    label="amending",
    instrument_kind="amending",
    suppress_front_matter_containers=True,
)

BY_LABEL = {p.label: p for p in (ACTS, RULES, AMENDING)}


def _demo() -> None:
    # The Acts profile is the conservative one: every corpus-specific widening is off,
    # so an Acts document reads exactly as it did before the two forks were merged.
    assert ACTS.instrument_kind is None
    assert (ACTS.ordinal_gap_max, ACTS.ordinal_dtop_max) == (1.0, 2.5)
    assert not any((ACTS.reattach_raised_ordinals, ACTS.folio_parenthesised,
                    ACTS.folio_running_title, ACTS.subchapter_rows,
                    ACTS.toc_hyphen_leaders, ACTS.toc_codeless_rows,
                    ACTS.notifying_sro))
    assert ACTS.toc_tail_density_floor is None
    # Every amending-specific behaviour is OFF for the consolidated corpora, so
    # adding the family changes no existing Acts or Rules document.
    assert not ACTS.suppress_front_matter_containers
    assert not RULES.suppress_front_matter_containers
    assert AMENDING.suppress_front_matter_containers
    assert AMENDING.instrument_kind == "amending"
    # ...and the amending profile inherits every Acts printer setting unchanged.
    assert (AMENDING.ordinal_gap_max, AMENDING.ordinal_dtop_max) == \
           (ACTS.ordinal_gap_max, ACTS.ordinal_dtop_max)
    assert not AMENDING.notifying_sro and not AMENDING.folio_parenthesised
    assert BY_LABEL["amending"] is AMENDING
    assert RULES.instrument_kind == "rules"
    assert (RULES.ordinal_gap_max, RULES.ordinal_dtop_max) == (2.5, 6.0)
    assert BY_LABEL["acts"] is ACTS and BY_LABEL["rules"] is RULES
    # frozen: a profile cannot be edited mid-conversion
    try:
        ACTS.subchapter_rows = True  # type: ignore[misc]
    except Exception:
        pass
    else:  # pragma: no cover
        raise AssertionError("Profile must be frozen")
    print("profiles self-check passed")


if __name__ == "__main__":
    _demo()

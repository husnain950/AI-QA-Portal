# Uppercase-suffixed citation markers — 22 sites, Customs 1969 (30.06.2025)

Board row 1. `grammar.MARKER` allowed a **lowercase** suffix only, so a marker printed
`66A` built no footnote record and rendered as literal body text.

## The defect, measured from the PDF and not from the ledger

The register could not be the instrument here — the invariants share the parser's marker
grammar, so they were blind to exactly the population that failed. Measured instead at the
word level, where the discrimination actually lives:

| | |
|---|---|
| dominant body size | **12.0pt** (72,785 words) |
| footnote-text size | 9.0pt (29,215) |
| **marker band** | **8.04pt** (1,710) |
| uppercase-suffixed markers in the band | **22 occurrences, 11 distinct, 13 pages** |
| lowercase-suffixed markers in the band (the control that always parsed) | 86 |

```
59&59A x6   27/27A x3   2/2A x3    59/59A x2   2A x2
66A x1      66B x1      30A x1     36/36A x1   14/14A x1   18/18A x1
```

That is the ledger's 22 exactly, reproduced independently. It is a **case inconsistency in
the source's own marker printing**, not a size or layout problem: the same document prints 86
lowercase-suffixed markers in the same band that have always parsed.

## The open question, and the pages that answered it

`open-work.md` blocked this row on a source question, correctly: if the *note* for `66A` were
printed `66a.`, the fix would be a case-fold on the citation join, and widening the class
would mint a marker resolving to nothing. The affected body pages carry no footnote block, so
the definitions had to be found first.

**They are on p77, and they are uppercase.** p77 is a consolidated notes page:

```
59A..  Omitted the words "bill of entry or" by the Finance Act, 2006.
59B.   Inserted by the Finance Act, 2002.
66A.   By Finance Act, 2006, the words "export duty" were substituted..
66B.   Substituted for full stop by Finance Act 1992.
```

against the markers on p65 at 8.04pt:

```
31. Date for determination of rate of 66A [duty on goods exported].- The rate and
... the export of any goods is permitted without a 59&59A [ goods declaration] ...
... loading of the goods on the outgoing conveyance commences 66B [:]
```

Marker and note agree on case. **No case-fold is needed** — the two sides widen together.
Document-wide there are 20 uppercase note heads at 9.0pt against 49 lowercase ones.

## What keeps this off a section code

`79A` is a real section code in this document, and `155A`…`155R`, `32A`, `26B`, `129A` all
print at body size as codes. **The regex was never the discriminator — the size gate is.**
`pagemodel.Word.marker_run` refuses anything above `cal.marker_max_size` *before* the token
grammar is consulted (`pagemodel.py:140`), and the footnote side gates on
`cal.footnote_marker_max_size` (`pagemodel.py:276`, `footnotes.py:125`). At 9.4 and 9.0 for
this lane, a marker at 8.04pt and a note at 9.0pt pass; a code at 12.0pt cannot. Verified
before the class was touched, because the widening is only safe while that gate stands.

## THE FIRST FIX WAS WRONG, and the register could not see it

The obvious change — widen `MARKER` to `[A-Za-z]` — took Customs from 0 of 22 visible to 22
visible and 13 bound, and generalised across 20 editions: 288 citations bound over 43
documents. It also **lifted 56 section cross-references in Sales Tax Rules 2006 (01-01-2025)
into `<sup>`**, `72A` ×30 out of "by virtue of section **72A** of the Sales Tax Act, 1990",
along with `150S`, `164A`, `39O`, `111A`.

**The register was 0 before and 0 after. It would have shipped the corruption silently**, and
so would CI, and so would the three lane suites. The only thing that caught it was reading the
rendered html of a document the round was not about.

**The lowercase restriction was never an oversight — it was the discriminator.** A section
code is uppercase and gets quoted constantly in prose; the case class is what separated the
two populations. `open-work.md` said "do not widen `MARKER` globally" and was right for a
better reason than it gave.

### Why the size gate cannot do the job, measured

| | Customs 30.06.2025 | Sales Tax Rules 01-01-2025 |
|---|---|---|
| `body_size` | 12.0 | 12.0 |
| `footnote_size` | 9.0 | **11.0** |
| `marker_max_size` (`body_size - 1.5`) | 10.5 | 10.5 |
| `footnote_marker_max_size` | 10.5 | **0.0 — no footnote zone at all** |
| the token in question | markers at **8.04** | `72A` at **9.0** |

`marker_max_size` is 10.5 in both, so it admits everything either document prints below body
size — including footnote prose. And the obvious repair, "admit uppercase only below footnote
prose size", **fails on the second document**, because `calibrate` puts its `footnote_size` at
11.0 and 9.0 < 11.0. Two attempts passed their unit checks on that reasoning and still
corrupted the document.

### The gate that works: `Word.upper_ok`

Two conditions, each pinned against the document that breaks it:

- **The document must have a footnote zone.** `footnote_marker_max_size == 0.0` means
  `calibrate` found none, and that rules document **has 0 footnote records on `main`** — so
  every uppercase token in it is a section code by construction.
- **The word must be strictly smaller than footnote prose** — raised, not merely small. In
  Customs that is 8.04 against 9.0, and that 1pt is the whole signal.

And one bug the gate exposed: `_is_marker_word` and `marker_token` read the **same word** on
the note-head path, so admitting uppercase in one and not the other recorded the raw text as
the note's key and the inline citation never found it. That is why an intermediate version saw
all 22 markers and bound none.

## Two classes, not one

The board named `grammar.py:132` and stopped there.

- **`MARKER` (`:132`)** — `[a-z]?` → `[A-Za-z]?`. `MARKER_RE` and `MARKER_NOTE_RE` are built
  from it, so both sides of the join widen at once.
- **`_MARKER_PARTS_RE` (`:139`)** carries *the same lowercase-only class* and feeds
  `marker_sort_key` (`:268`). Widening `MARKER` alone leaves this one refusing `66A`,
  `marker_sort_key` falls to its `(10**6, t)` catch-all, and every uppercase-suffixed note
  sorts to the end of the document instead of beside its numeric sibling — **a silent
  ordering bug hidden behind a fixed rendering one**, and `inv_footnotes_in_numeric_order`
  could not have caught it: it sees order, not correctness of the key.
- The suffix is compared **case-folded** in `marker_sort_key`, so `66A` sorts where `66a`
  would. Raw, ASCII puts every uppercase suffix ahead of every lowercase one.

`MARKER_PREFIX` (`:190`) and `footnotes._MARKER_PREFIX` (`:177`) were left alone: no marker in
this population sits in a heading prefix, and neither pattern is reached by the 22.

## Result: 0 of 22 visible → 22 visible, 13 bound

Under the gated fix, re-converted and diffed against `main`'s output. The rules document that
the ungated version corrupted comes out **byte-identical to `main`** — 854 `<sup>`, 0 footnote
records, 0 uppercase — which is the control this round needed and did not have at first:

| | before | after |
|---|---|---|
| uppercase-suffixed **resolved citations** (`<sup class="cite">`) | **0** | **13** |
| uppercase-suffixed **unresolved markers** (`<sup class="marker">`) | 0 | 9 |
| `<sup>` of any kind in the document | 920 | **959** |
| footnote records built | 801 | **818** |

Bound: `2A` ×5, `27A` ×3, and `66A`, `66B`, `30A`, `14A`, `18A` once each. Section 31 went
from 2 footnote records to 5; section 30 from 6 to 7. Sales Tax Rules 2006 (01-01-2025),
the control: `<sup>` 854 → 854, notes 0 → 0, uppercase 0 → 0.

**Before, none of the 22 was even a marker** — each was literal body text. Now every one is a
marker and 13 resolve. The 9 that do not are blocked by two *source* defects, both measured:

- **`59A` ×8 — the note head is printed `59A..`, with two dots.** p77 carries it at 9.0pt and
  `MARKER_NOTE_RE` is `^(MARKER)\.?$`, which reads one. A real, readable note that our
  pattern refuses. **A different cause from this round — see the row below.**
- **`36A` ×1 — there is no note.** `36A` appears nowhere in the document as a note head, at
  any size. The source cites a note it never defines, and `<sup class="marker">` is exactly
  the designed rendering for a marker with no note (`inv_leading_marker_cited`'s docstring
  says so). Nothing to fix.

## The board's prediction was wrong, and the reason is worth keeping

`tasks.md` row 1 and `open-work.md` item 11 both said: **"expect the register to rise when the
invariant is widened and fall when the parser is."** Measured here, widening
`_LEADING_AMEND_MARKER` to either case against the un-re-converted corpus moved the register
by **zero** — not the 0 → 61 that round 21's widening produced.

`inv_leading_marker_cited` only fires on a leaf that **opens** with an amendment marker *and*
renders no `<sup>` at all. All 22 of these are inline, mid-sentence, in leaves that already
carry other citations. Round 21's 0 → 61 came from the **run form** (`7,45[`, `5&7[`), which
does appear leading. The rise-then-fall shape is a property of *that* class, not of every
marker-grammar class, and inheriting the prediction cost this round a measurement to disprove.

The invariant was widened anyway, and should stay widened: an instrument narrower than the
defect cannot measure a future regression in it, whatever it measures today.

## Traced, not taken: note heads printed with a double dot

Found while measuring the 9 above. Nine tokens in this document print a note head with two
dots where 732 print one:

```
2005.. x2 (p127, p246)   130.. (p30)    40.. (p75)    59A.. (p77)
5..    (p127)            230.. (p199)   1b..  (p245)  26..   (p274)
```

Two are years and `is_year_like` refuses them for an unrelated and correct reason. **The other
seven are real notes that bind to nothing today** — and only one of them, `59A`, is
uppercase, so this class has been silently costing the lowercase population too and nobody
has looked. The fix is plausibly `\.{0,2}` in `MARKER_NOTE_RE`, but it widens note-head
detection corpus-wide and needs its own measurement of what it mints. **A different cause: it
is not batched into this round.**

## Blast radius, gated vs ungated

Both measured over a full re-conversion of the 77 text-layer acts and rules documents.

| | ungated (`MARKER` widened) | **gated (`upper_ok`)** |
|---|---|---|
| documents touched | 43 | **21** |
| citations bound, acts | 288 | **288** |
| unresolved markers, acts | 213 | 195 |
| **rules lifts** | **82 across 5 documents** | **1** |

The gate removes 22 documents and 81 of the 82 rules lifts **without losing a single
binding**. The one that remains is correct: Customs Rules 2001 (30.06.2023) s.228 prints
`23A[excluding M/s. al-Tuwairqi Steel Mills Karachi]` — a genuine amendment marker in the
`marker[substituted text]` shape, rendered `<sup class="marker">` because its note is not
found. That document has a real footnote zone, so the gate admits it, correctly.

The 288 are one class across 20 Customs editions, 12-15 per edition: the same source, the
same sections, carried through every amendment.

## Verification

```
grammar._demo / pagemodel._demo   pass -- both gate conditions pinned against the
                                  document that breaks each one
test_register_snapshot.py --write  total 0, no diff -- see below
run_tests_smoke.py                 ordinance 12 / acts 80 / rules 11 editions pass
pytest tools/tests                 234 passed, 1 skipped
re-conversion                      77 of 77 text-layer acts+rules, 0 failures, 16 min
data/ocr_cache                     0 B
```

`run_tests_smoke.py` also reports `FAIL tools/discover_corpus.py --check: signatures.json is
stale`. Pre-existing and unrelated — last written at round 6, import chain untouched here;
diagnosed in full in PR #100.

**The register is 0 before and 0 after, and this PR does not change `register.json`.** That
is not a null result, it is the point: no invariant in this repo can see this class, in either
direction. The proof of the fix is the output diff and the control document, and the proof
that the *first* fix was wrong was also the output diff — the register said 0 through all of
it.

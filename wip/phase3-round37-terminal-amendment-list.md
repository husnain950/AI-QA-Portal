# A terminal amendment-source list, read as body — Customs Rules 2001, 665 markers

Round 37. Not a board row: the board had no register-bearing work left, so this comes off
the **unmeasured surface** — the 3,930 unresolved `<sup class="marker">` across 82 documents
that no invariant watches. Customs Rules 2001 (30.06.2023) was 665 of them, the second
largest single block, and the only one of the two largest that had a calibrated footnote
zone.

## The page is the authority, and it said the notes were printed

The ledger's hypothesis for a document with 665 markers and **zero** footnote records is
that its markers are unresolvable. Reading the source disproves it in three pages.

Customs Rules 2001 does not print per-page footnotes at all. It prints its amendment
apparatus **once, at the end of the document**: page 561 opens `As Amended:-` and pages
561–563 carry 158 numbered entries, one per notification that amended the rules.

```
p561  As Amended:-
      1. S.R.O.247(I)/2002, - dated 08.05.2002.
      2. S.R.O.375(I)/2002, - dated 15.06.2002.
      …
      23A. S.R.O.23(I)/2006 - dated 05.01.2006          ← the interpolated lettered entry
      52. S.R.O.___(I)/2010 - dated 24.05.2010.
p562  53 S.R.O.510(I)/2010 - dated 11.06.2010           ← the source drops this dot
      …
p563  157. S.R.O.1093(I)/2023 - dated 23.08.2023
```

Every marker the body cites is one of them: **107 distinct markers, all plain numbers, all
inside 1..157, none outside**. Zero notes was not the truth about this document; it was the
parser reading its whole apparatus as statutory text.

## Why every gate in `footnotes.py` missed it

The apparatus is set at **body size**, and the module is calibrated for a footnote-sized one.
Three independent gates each refuse it, and no one of them is wrong:

| gate | what it wants | what the list is |
|---|---|---|
| `_size_zone_top` (`pagemodel.py:354`) | a changepoint from body-size lines to footnote-size lines | all 159 lines are 10.0pt, the body size — `small` is false throughout, so `best_k = n` |
| `_is_marker_word` (`footnotes.py:125`) | `w.size <= cal.footnote_marker_max_size` = **9.0** | the entry numbers are 10.0pt |
| `_is_amendment_note` (`pagemodel.py:321`) | an edit verb — *substituted, inserted, omitted…* | `S.R.O.247(I)/2002, - dated 08.05.2002.` carries none |

So the whole block arrived in `body_refs`, and rule **1122 (*Audit*)** — the last rule in the
document, ending on page 560 — swallowed all 157 notification lines as its own text.

**Loosening those three gates was rejected.** Each is load-bearing for the documents it was
measured on — the size tests are what keep a body line that merely *opens* with a superscript
out of the zone, and `pagemodel.py:296-307` records the 14 `section_carries_its_body` failures
across 13 editions that followed the last time one of them was too generous. A terminal
apparatus is not a footnote zone in the first place; it is read as its own shape instead.

## The change

`footnotes.py` gains a reader for the apparatus, and `pipeline.py` cuts it out of the body
before sections are assembled.

```python
_AMEND_LIST_CAPTION_RE = re.compile(r"^\s*as\s+amended\s*:?\s*[-–—]?\s*$", re.I)
_AMEND_LIST_ENTRY_RE   = re.compile(r"^\s*(?P<marker>\d{1,3}[A-Z]?)\s*[.)]?\s+(?=S\.?\s*R\.?\s*O)", re.I)
```

**The caption alone is not the gate.** "as amended:-" is ordinary statutory prose, and cutting
the body at one would silently delete everything below it. `amendment_list_start` also requires
that essentially every non-empty line under the caption is a numbered notification entry —
at least 5 of them, and at least 80% of what follows. Both halves are pinned by their own
negative test.

The notes are pinned to the page that **prints** them, which is what every ref and the orphan
net read. Binding then costs nothing new: each of the 158 markers occurs exactly once
document-wide, so `_citation_scope`'s existing unique-marker path (`pipeline.py:282-288`)
resolves it from anywhere in the body — which is the whole reason an apparatus 400 pages away
from its citations can work at all.

## Result on the document

Re-converted from a clean tree and diffed against `_pre_37`:

| | before | after |
|---|---|---|
| `<sup class="marker">` (unresolved) | **665** | **0** |
| `<sup class="cite">` (bound) | 0 | **672** |
| footnote records | 0 | **421** (158 distinct notes, on 229 leaves) |
| leaves | 1,105 | 1,105 |
| leaves gained / lost | — | **0 / 0** |
| body words | 256,844 | 256,048 |
| leaves whose *text* changed | — | **1** |

The one leaf is rule 1122, **−796 words**: the 157 notification lines leaving a rule about
*Audit*. Its `end_page` goes 563 → 560, and its body now ends where the source ends it, on
`(Manzoor Ahmad) / Member (Customs)`.

**672 is seven more than 665, and all seven are a gain, not an invention.** Five are markers
printed inside table cells that previously rendered as literal text — `31[S.No.`, `45[3.`,
`50[5`, and `93[ROUTES` twice; the other two are the `2&30` run on the CHAPTER XIV caption,
below. Nothing that was a citation stopped being one, and the baseline is a conversion of
this document at `c0352da` (`main`), not a stored output.

## The register moved, and that is the interesting half

`footnote_on_citing_leaf` went 0 → 1 on this document:

```
footnote 561.2 attached to 325 (Repeal) but cited by 1018 (Format for CMR consignment n)
```

It is not a false alarm and it was not caused by the new reader. It was **revealed** by it:
a document with zero footnote records passes every footnote invariant in the suite, because
there is nothing for them to look at. **An invariant with nothing to measure is not passing,
it is unmeasured.**

Source page 102 is the evidence. Rule 325's repeal table ends at row 21, and the next line is
the caption of CHAPTER XIV, printed with its amendment markers glued to the bracket:

```
top=342.5  x0=132.1  10.0pt   21. S.R.O. 1319(I)/1996 24.11.1996
top=376.3  x0=291.1   6.5pt   2&30
top=377.1  x0=305.7  10.0pt   [CHAPTER XIV
top=400.0  x0=291.2  10.0pt   TRANSSHIPMENT
```

`tables.find_table_spans` extends a span on a **margin** test — a line is still in the table
while it starts at or right of the table's first column — and a *centred* caption sits well to
the right of it. So both caption lines were folded into the last data row:

```html
<td>S.R.O. 1319(I)/1996 2&amp;30</td><td>24.11.1996 [CHAPTER XIV TRANSSHIPMENT</td>
```

The caption's own markers `2` and `30` were still registered as citations of leaf 325 while
rendering as literal cell text, so once the notes existed they were attached to a leaf whose
html shows no `<sup>` at all — which is exactly what the invariant says.

`pagemodel` already guards the **grid** path against this ("never swallow a structural heading
into a table just because it grazes the bbox", `pagemodel.py:1620-1635`). The gridless
fallback had no equivalent. It does now: a span stops at a CHAPTER / PART / Division caption.

The decoration class is the part to read twice. The source prints the marker **run** `2&30`
glued to the bracket, and `builder._STRUCT_DECOR_RE` spells the single-marker form only, so a
local `_CAPTION_DECOR_RE` strips runs as well. `_CAPTION_RE` is anchored at **both** ends, so
a data row — which carries its other columns on the same line — can never match it, whatever
a cell happens to say.

## What this does NOT fix, and it is worth saying plainly

`2&30 [CHAPTER XIV` still does not become a **structural boundary**. `builder._STRUCT_DECOR_RE`
reads one marker, not a run, so the caption is not recognised anywhere else either:
**CHAPTER XIV is absent from the tree** and rules 326–340 are parented under CHAPTER XIII.
Two more captions are missing from the same document for two more reasons. That is a
different cause and it has its own row in `handover/tasks.md`; it is not batched here.

## The control: 76 of 77 documents are byte-identical

Both changes are gated on shapes the rest of the corpus does not print, and the whole staged
text-layer set was re-converted from a clean tree (`0139b858daac`) to prove it rather than
argue it. Every acts and rules output was diffed against `_pre_37` on five measures plus
per-leaf `html` and `plain_text`:

| | |
|---|---|
| documents re-converted | **77** (66 acts + 11 rules), 0 failures, 953s |
| documents skipped | 14, image-backed — the no-OCR decision, `data/ocr_cache` still 0 B |
| **documents changed** | **1** |
| documents byte-identical (leaf html + plain_text + all five measures) | **76** |

The caption scan says the same thing about the reader independently: of all **100** staged
text-layer sources, exactly **one** prints a terminal `As Amended:-` list, and no other
document carries more than five numbered S.R.O. lines in its last twelve pages.

The ordinance lane is untouchable by either change: it runs `packages/fbr_ingest`, which does
not import `legal_ingest` at all. **No port, no ordinance re-conversion.**

## Corpus-wide, this is 17% of the unmeasured population

The census that picked this round, re-run after it:

| | before | after |
|---|---|---|
| unresolved `<sup class="marker">` | **3,930** | **3,265** |
| documents carrying them | 82 | **81** |
| acts / rules / ordinance | 1,900 / 1,599 / 431 | 1,900 / **934** / 431 |

The largest remaining single block is Sales Tax Rules 2006 (01-01-2025) at **869**, and it is
a different cause — its notes *are* printed per page; calibration reads the page folio as
`footnote_size`. Traced during this round and written up as its own board row.

## The corpus is now at ONE revision for every document that can reach it

| documents | `pipeline_revision` |
|---|---|
| **77** (66 acts + 11 rules) | **`0139b858daac`** — this round |
| 14 (acts) | *(none)* — image-backed, permanently, under the no-OCR decision |
| 9 (ordinance) | `dbcab2f79b78` — `fbr_ingest`, untouched by this round |
| 3 (ordinance) | `4827840c191f` — image-backed ITO editions |

The 21/56 acts+rules split round 36 left behind is gone; those two lanes are uniform.

## Verification

```
pytest tools/tests                     245 passed, 1 skipped
run_suite.py acts / rules / ordinance  ALL PASS on every document, all three lanes
test_register_snapshot.py --write      total 0 — no diff to register.json
ruff check (bare)                      All checks passed
du -sh data/ocr_cache                  0B
re-conversion                          77 of 77, 0 failures, 953s, clean tree
corpus diff vs _pre_37                 1 document changed of 77
```

`run_tests_smoke.py` reports `FAIL tools/discover_corpus.py --check: signatures.json is
stale`. **Pre-existing and unrelated** — run side by side against a worktree at `c0352da`
during this round, and both print the identical 20-line CHANGED list.

## Rejected

- **Loosening `footnote_marker_max_size`, `_size_zone_top` or `_is_amendment_note`** to let
  the terminal list through the footnote-zone path. Each gate is load-bearing for the
  documents it was measured on, and a body-size apparatus printed once at the end of a
  document is not a footnote zone — reading it as one would mean teaching three separate
  components to accept body-sized notes with no edit verb.
- **Cutting the body at the caption alone.** "as amended:-" is ordinary statutory prose. The
  share-and-count gate is what makes the cut safe, and `test_the_caption_alone_does_not_cut_the_document`
  is the pin.
- **Widening `builder._STRUCT_DECOR_RE` to strip a marker RUN**, which would make
  `2&30 [CHAPTER XIV` a real structural boundary and recover the missing chapter. That is a
  boundary change across every document in the corpus, it is a different cause, and rounds 13,
  18 and 27 are all on record about what happens when a boundary widening is batched into
  another round. It has its own board row instead.
- **Exempting `footnote_on_citing_leaf` on this document.** The hit is a live parser defect
  with a source page behind it, and an exemption silences the whole invariant for the whole
  document — on the one document that just gained its first 421 footnote records, which is
  precisely where that instrument is now worth the most.

# Round 42 — a marker RUN is leading decoration too, whatever separates it

**Row 14.** Customs Rules 2001 carried **41 chapters where the source prints 44**. Two of
the three are now recovered and the third is refused **on measured evidence**, not left
untried. Chapters **41 → 43**, leaves **1,105 → 1,106**.

## The ledger was wrong about which three

Row 14 said two of the three were traced and the third — CHAPTER VIII — was *"not traced;
no caption is printed between CHAPTER VII (p21) and CHAPTER IX (p34)… so it may be an
omission in the source."*

**The caption is printed, on p21, and it is the same defect as CHAPTER XIV:**

```
p21    CHAPTER VII
p21    41&46 [CHAPTER VIII          LICENSING OF CUSTOMS AGENTS
p102   2&30 [CHAPTER XIV            TRANSSHIPMENT
p163   “Chapter XX
```

So it is **two causes, not three**, and CHAPTER VII and VIII start on the same page — which
is why the row thought nothing was printed between VII and IX.

The row's other claim, that *"rules 127-132 are absent from the body"*, is **true and
unrelated**. The source prints `127.` … `132.` only inside the terminal
`As Amended:-` S.R.O. list that round 37 taught the parser to cut out
(`127. S.R.O.1055(I)/2021 - dated 18.08.2021`). They are numbered notification entries, not
rule bodies. Nothing is missing.

## The defect

`builder._STRUCT_DECOR_RE` strips leading amendment decoration before asking whether a line
is a container heading:

```python
_STRUCT_DECOR_RE = re.compile(r"^(?:[\d*]{1,3}\s*|\[+\s*)+")
```

Between stacked markers it knew only **whitespace**. On `2&30 [CHAPTER XIV` it therefore
matched `2`, stopped at the ampersand and left `&30 [CHAPTER XIV`, which matches no heading
form. The line was never a boundary, so:

| | before |
|---|---|
| CHAPTER XIII | 33 leaves, running to rule **340** |
| CHAPTER VII | 19 leaves, holding CHAPTER VIII's whole run |
| CHAPTER VIII / XIV | absent from the tree |

**The grammar already knew.** `grammar.MARKER_PREFIX` has admitted `,` and `&` since the
round that measured them, and `grammar._MARKER_RUN_SEP_RE` is exactly `\s*[,&/]\s*` — "the
separators that fuse several markers into ONE extracted word". This was a **second, narrower
implementation of the same idea**, and the fix is to spell it the way the grammar does.

The suite carries a third, independent implementation (`_common._STRUCT_DECOR`) with the
same narrow spelling. It is widened in step: the three readers may differ, but they may not
disagree — `test_structural_boundary_agrees_with_grammar` is that comparison.

**And there is a fourth, which already had it right.** `tables._CAPTION_DECOR_RE`, added by
round 37, reads:

```python
#: Leading amendment decoration on a structural caption: a marker, or a RUN of
#: markers joined the way the source prints them ("2&30"), and the bracket that
#: opens the amended text.  ``builder._STRUCT_DECOR_RE`` spells the single-marker
#: form; the run form is what page 102 of Customs Rules 2001 prints.
_CAPTION_DECOR_RE = re.compile(r"^(?:[\d*]{1,4}(?:\s*[,&/]\s*[\d*]{1,4})*\s*|\[+\s*)+")
```

Round 37 met this exact line, on this exact page, wrote the run form for its own use and
recorded in a comment that `builder`'s was the narrow one. It did not widen `builder`,
because doing so re-parents sections and that was row 14's job. This round is that job, and
the comment is the corroboration.

One drift is deliberately **not** closed here: `tables` and `grammar.MARKER_PREFIX` allow a
**four**-digit marker (`[\d*]{1,4}`) where `builder` and the suite allow three. The defect
measured is the separator, not the digit count, and widening the count is a separate,
unmeasured change. It is recorded rather than bundled.

## The third chapter is refused, and this is why

`“Chapter XX` (p163) *is* a substituted caption, and admitting the opening quote as
decoration looked like a free third chapter. It was measured first.

**The same glyph opens QUOTED REPEALED TEXT, and that is the commoner reading.** Customs Act
1969, p219, in full:

```
      THE CUSTOMS ACT,1969
      1 [ CHAPTER XIX-A                 ← the LIVE chapter; already cut today
      SETTLEMENT OF CASES
      2 [ 196-K Omitted.
      …
      196-U Omitted.]
      LEGAL REFERENCE
      1. Inserted by the Finance Act, 1996 (IX of 1996), S.4(5), page 471.
      2. Omitted by the Finance Ordinance, 2000 (XXI of 2000), S.4(13), page 204. At the
      time of omission section 196-K to 196-U were as under:
      “Chapter XIX-A                    ← quoted history
      SETTLEMENT CASES
      196-K. Indirect Taxes Settlement Commission.- (1) The Federal Government …
```

`CHAPTER XIX-A` is **already in that document's tree**, cut from the live
`1 [ CHAPTER XIX-A` sixteen lines above. Cutting at the quoted one would mint a **duplicate
chapter and re-parent eleven repealed sections as live law**, in at least twenty Customs
editions.

The suite refuses the identical line for the identical reason — `_QUOTE_CUE` in
`suite/invariants/_common.py`, *"a repealed Part/Division heading QUOTED below an amendment
note is legitimate history, not a boundary"*. Telling the two apart needs quote-**territory**
tracking, which is a different change from this one. Both lines are now pinned in
`NOT_BOUNDARIES`.

## The gained/lost census

Row 14 said *"this is a boundary widening: it re-parents sections… measure it as gained/lost
over all 187 sources first."* Measured over the **143 acts and rules sources**, against
`calibrate._page_lines` — the parser's own line text:

| regex | lines GAINED | lines LOST | documents |
|---|---|---|---|
| **shipped** (marker-run separators) | **2** | **0** | **1** |
| rejected (marker-run **+ opening quote**) | 68 | 0 | 31 |

The two gains are the whole of it:

```
[rules] Customs Rules, 2001 (Updated Up to 30.06.2023)  p21   '41&46 [CHAPTER VIII'
[rules] Customs Rules, 2001 (Updated Up to 30.06.2023)  p102  '2&30 [CHAPTER XIV'
```

Nothing is lost anywhere. The 66 lines the quote half would additionally have cut are led by
**`“Chapter XIX-A` ×19** — the duplicate-chapter case above, in nineteen Customs editions —
followed by quoted `Division` and `CHAPTER` captions of the same kind. (Two sources error:
one is a `.docx` and one is not a PDF; both are known non-PDF entries in the corpus.)

### The first census was wrong, and how

The first pass screened every corpus line through `signature.extract_text` and reported the
marker-run class as **zero gains**. That extractor **drops the superscript run entirely** —
it hands p102 over as `[CHAPTER XIV`, which the narrow regex already accepted — so the class
the census existed to measure was invisible to it. This is `working-rules.md`'s *"measure
against the parser's line text, not the rendered output"*, and it now has a second instance.

A second pass over `_page_lines` inside a `ProcessPoolExecutor`, A/B-ing the two regexes by
assigning to the module global, disagreed with a direct call on the same document (3 gains
vs 0). Passing the pattern into a local copy of the three-line predicate removed the global
entirely; that is the run above.

## Measured

One document changes. Converted from a clean tree (`fea1cc5bac2c`, no `-dirty`) against a
baseline regenerated from a worktree at `cb11b49`.

| | before | after |
|---|---|---|
| chapters | 41 | **43** |
| leaves | 1,105 | **1,106** |
| CHAPTER VII | 19 | **3** |
| CHAPTER VIII | — | **17** |
| CHAPTER XIII | 33 | **12** |
| CHAPTER XIV | — | **21** |
| `<sup class="cite">` | 660 | 656 (−4) |
| `<table>` / `<tr>` | 167 / 1,423 | **unchanged** |
| body words | 256,038 | 256,030 (−8) |

**The re-parenting is exact.** XIII's 33 become 12 + XIV's 21. VII's 19 become 3 + VIII's 17,
plus one leaf that did not exist before.

### The new leaf is a real rule

```
89. If the 90[Additional Collector of Customs] is so satisfied, he would permit re-export
    of the frustrated cargo under Customs supervision without payment of duties …
```

Rule 89 was glued into its neighbour while the chapter caption sat unrecognised in the body.
It now cites marker `562.90`, which is why that note's owner list gains `89`.

### The −4 citations are all spurious, and round 37 predicted them

| ref | owners before | owners after |
|---|---|---|
| `561.2` | **325**, 1018 | 1018 |
| `561.41` | **88**, 568 | 568 |
| `561.46` | **88**, 235, 297, 350, 352 | 235, 297, 350, 352 |

Leaf 325 was swallowing `2&30 [CHAPTER XIV` and leaf 88 was swallowing
`41&46 [CHAPTER VIII`, so the captions' own markers were registered as citations **of the
leaf that swallowed them**. Round 37's `u1b` recorded exactly this shape and said of it:
*"NOT fixed by it: `2&30 [CHAPTER XIV` is still not a structural boundary — that is row 14."*
This is that residue.

The −8 body words are the two caption lines and their titles moving out of leaf text into
container nodes. `LICENSING`, `TRANSSHIPMENT`, `frustrated cargo` and `consumers of PTA` each
appear the same number of times before and after.

## Gates

**The invariant reports this defect, and that is a per-defect gate, not an assertion.** With
the suite's reader widened and the corpus NOT yet re-converted, the register moved:

```
rules: {"no_structural_heading_in_body": 2}
  - section 88:  structural heading in body: '41&46[CHAPTER VIII'
  - section 325: structural heading in body: '2&30[CHAPTER XIV'
```

Re-converting takes it back to `{}`. Rise on the invariant, fall on the parser, register
unchanged at 0 — and the two hits name the two defects.

```
pytest tools/tests          310 passed, 1 skipped
test_register_snapshot      passes (0 after re-conversion; 2 before)
run_tests_smoke.py          ordinance 12, acts 80, rules 11 -- all pass
ruff check                  All checks passed!
discover_corpus --check     exit 1, the same 27 as main -- row q3, PR #107
```

## What this leaves

- **CHAPTER XX**, refused above. It needs quote-territory tracking in the parser, mirroring
  the suite's `_QUOTE_CUE`. Its own row.
- **The `fbr_ingest` fork** has its own copy of this decoration strip and is not ported here;
  the ordinance lane's own census has not been taken.

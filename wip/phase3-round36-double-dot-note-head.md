# Note heads printed with a DOUBLE dot — 6 sites, 20 Customs editions

Board row 1, the last open register-bearing row. `grammar.MARKER_NOTE_RE` was
`^(MARKER)\.?$` — **one** trailing dot. The Customs Act source prints a few of its note
heads with two, so `parse_footnotes` never opened a note on those lines.

The text was not lost, which is why nothing ever reported it: `footnotes.py:1242` folds a
non-candidate line into the **previous** note's body. So the corpus carried notes that were
wrong at both ends — the real note had no record and no key, and its neighbour carried
prose that was never its own.

## The board's numbers were wrong, and the page is the authority

`handover/tasks.md` row 1 said **nine** double-dot note heads, of which *"the other seven
are real notes that bind to nothing"*. Scanning the **first word of every line** of all 279
pages of the 30.06.2025 edition — the parser's view, not the rendered `plain_text` — finds
**six**, and all six are real note heads:

| pdf page | token | x0 | the note text that follows |
|---|---|---|---|
| 75 | `40..` | 129.6 | Amended by the Finance Act, 2006. At the time of amendments … |
| 77 | `59A..` | 129.6 | Omitted the words "bill of entry or" by the Finance Act, 2006. |
| 127 | `5..` | 129.6 | By the Finance Act, 2006, the words "bill of export or" … |
| 245 | `1b..` | **165.6** | Substituted for the words "Central Government" … |
| 274 | `26..` | 129.6 | Inserted section 211A by the Finance Act, 2006. |
| 275 | `39..` | 129.6 | Added by the Finance Act, 1975 (L of 1975), S.7(7), page 10. |

Two corrections, and both matter to the fix:

- **`130..` (p30), `230..` (p199) and `2005..` ×2 (p127/p246) are not note heads and never
  could be.** They are `…, page 230..` and `… Finance Act, 2005..` — a sentence-ending dot
  after a page citation or a year, printed **mid-line**. `parse_footnotes` reads `words[0]`
  only (`footnotes.py:1220`), so no widening of this pattern can reach them. The board
  counted four tokens that were never in play.
- **`39..` on p275 is a real note head the board never listed.**

`1b..` prints at x0 165.6 against a calibrated `footnote_marker_x_max` of ≈141.6
(`calibrate.py:520`). The left-margin gate refuses it, correctly — it is an indented
continuation line — and it has no inline citation waiting. **Five of the six mint.**

## What it mints, measured corpus-wide before the change

The board required *"its own measurement of what it mints"* before this class was widened.
Run over **all 91 staged text-layer acts + rules source files** (13 min), at the parser's
view: every line's first word, tested against `^(?:\d{1,4}[A-Za-z]?|\*)\.\.$`, reported with
its `x0` and size so the gates could be applied afterwards.

| | |
|---|---|
| documents scanned | **91**, 0 read errors |
| documents carrying the class | **20** — every Customs Act edition, and nothing else |
| double-dot first words | **119** (100 at the left margin, 19 indented `1b..`) |
| distinct tokens | `40..` `59A..` `5..` `26..` `39..` `1b..` |
| rules lane | **0** |
| **false positives** | **0** — every one of the 119 is followed by note prose |

The ordinance lane is untouchable by this change in any case: `packages/fbr_ingest` is a
separate fork with its own `_is_marker_word` (`fbr_ingest/footnotes.py:110-119`, a bare
`isdigit()` test) and does not import `legal_ingest.grammar`. **No port, no ordinance
re-conversion.**

## The change — two regexes

```python
:167  MARKER_NOTE_RE        = re.compile(rf"^({MARKER})\.{{0,2}}$")
:175  _MARKER_NOTE_RE_UPPER = re.compile(rf"^(?:({MARKER})\.{{0,2}}|({_MARKER_UPPER})\.{{1,2}})$")
```

**Two classes, not one** — round 35's lesson, and it applies here for the same reason.
`59A..` is on the **uppercase** branch and the other five on the lowercase one, and
`_is_marker_word` and the note-head key extraction read the **same word**
(`footnotes.py:1229-1233`): a head admitted by one and refused by the other records the raw
text as its key and the inline citation never finds it.

**The uppercase branch keeps its MANDATORY dot** — `\.{1,2}`, never `\.{0,2}`. A bare `72A`
read as a note head collapsed Sales Tax Rules 2006's footnote blocks from hundreds to zero
(the measurement is in the comment at `:168-174`). The only new admission anywhere in the
grammar is **exactly two dots**.

Nothing else moves, and the reasons are structural rather than measured:

- `marker_token` (`:241-251`) is the **only** executable use of either pattern, and
  `MARKER_NOTE_RE` is never imported outside `grammar.py`. `_is_marker_word`
  (`footnotes.py:136`), the note key (`:1234`) and the footnote-zone line test
  (`pagemodel.py:318`) all route through it.
- **The inline side is immune by construction.** `Word.marker_run` returns `[]` for any
  token ending in a dot *before* this grammar is consulted (`pagemodel.py:185-186`), so a
  wider note-head dot class cannot lift body text into `<sup>`. That is the failure mode
  round 35's first attempt had, and it cannot occur here.
- `_MARKER_PARTS_RE` / `marker_sort_key` see the **stripped** token, so ordering is
  untouched. `MARKER_PREFIX` is not on this path.
- `_accept_marker` still runs after the shape test: `is_year_like`, the `to/and/or/of/at`
  page-range guard, the bracketed-repeat guards and the quoted-heading guard are unchanged.

## Result — 254 citations bound, 0 lost, across 20 editions

Re-converted from a **clean** tree (`70d10d53cd75`, no `-dirty`) and diffed against the
`_pre_36` snapshot. Every edition moves identically:

| | before | after |
|---|---|---|
| footnote records | 12,843 | **12,963** (+120, six per edition) |
| `<sup class="cite">` | — | **+254** |
| `<sup class="marker">` (unresolved) | — | **−254** |
| new note refs | — | **100** (five per edition) |
| notes lost | — | **0** |

A one-for-one exchange: every citation gained is an unresolved marker that stopped being
unresolved. Nothing was invented.

On 30.06.2025, the document the class was traced on:

| | before | after |
|---|---|---|
| footnote records | 818 | **824** |
| `<sup class="cite">` | 914 | **926** |
| `<sup class="marker">` | 47 | **35** |

The twelve that moved are `59A` ×8 and `26`, `39`, `40`, `5` once each — exactly the
population predicted from the unresolved-marker census before the change.

### The five swallowing notes give back what was never theirs

This is the half a register cannot see, and it is the more important half:

```
53.39    was  'Omitted by Finance Act, 2005.\n40.. Amended by the Finance Act, 2006. ...'
         now  'Omitted by Finance Act, 2005.'
55.59    was  'Substituted by the Finance Act, 2003.\n59A.. Omitted the words "bill of entry or" ...'
         now  'Substituted by the Finance Act, 2003.'
105.4    was  'Inserted by the Finance Act, 2003 (I of 2003), S.5(27), page 31\n5.. By the Finance Act, 2006 ...'
         now  'Inserted by the Finance Act, 2003 (I of 2003), S.5(27), page 31'
252.25a  ...  same shape, 26.. removed
253.38a  ...  same shape, 39.. removed
```

**Total note words 28,551 → 28,545, −6.** The six words lost are the six `NN..` head tokens
themselves, which are no longer prose in anyone's note. Every other word is conserved and
now sits in the note that printed it.

### What did NOT move

- **Leaf counts, section/chapter/schedule counts and total body words are unchanged on all
  20 editions.** That is round 13's check, and it passes.
- **The footnote zone did not move.** `pagemodel._footnote_marker_line` (`:313`) also routes
  through `is_marker_text` and is what finds the zone top, so a new admission could in
  principle have pulled body text into the zone. Footnote page span on 30.06.2025 is
  **29..278 before and after**.
- **The control is byte-identical in its body.** Sales Tax Rules 2006 (01-01-2025) — the
  document round 35's first, wrong fix corrupted — re-converted under this change comes out
  identical apart from `converted_at` and `pipeline_revision`: 0 footnote records, 869
  `<sup class="marker">`, unchanged.
- **The register is 0 before and 0 after**, all three lanes, and every `RESULT` line is
  identical to the pre-round baseline. `register.json` is unchanged and this PR does not
  touch it.

That last line is not a null result, it is the point, and it is the second round running to
prove it: **no invariant in this repo can see this class in either direction.** The proof is
the output diff and the control document.

## What is left on these documents, and it is not this class

30.06.2025 still renders 35 `<sup class="marker">`. They are a different population —
`1` ×15, `8` ×2, `10` ×2, and singletons including `36A`, `193`, `194`, `196`, `228`.
`36A` is the one row 1 named beside the double dot: **the source cites a note it never
defines**, at any size, and `<sup class="marker">` is the designed rendering for exactly
that (`inv_leading_marker_cited`'s docstring). Nothing to fix.

## Verification

```
grammar._demo / pagemodel._demo    pass -- RED before the regex edit, green after
pytest tools/tests                 234 passed, 1 skipped
run_suite.py acts/rules/ordinance  ALL PASS, RESULT lines identical to baseline
test_register_snapshot.py --write  total 0, no diff to register.json
ruff check (bare)                  All checks passed
du -sh data/ocr_cache              0B
re-conversion                      21 of 21 (20 Customs + 1 control), 0 failures, 117s
```

`run_tests_smoke.py` reports `FAIL tools/discover_corpus.py --check: signatures.json is
stale`. **Pre-existing and unrelated** — reproduced identically on `main` at `8c201f5`;
diagnosed in PR #100.

## Rejected

- **`\.*` or `\.{0,3}`.** Nothing in 91 documents prints three dots on a note head. The
  bound stays where the evidence is, and `_demo` pins `40...` as *not* a marker.
- **Widening the uppercase branch's dot to optional.** That is the change that destroyed a
  rules document in round 35; it is pinned closed in `_demo`.
- **Admitting `1b..` by loosening the x0 gate.** It is an indented continuation line, the
  gate is right about it, and it has no citation waiting. The gate was not touched.

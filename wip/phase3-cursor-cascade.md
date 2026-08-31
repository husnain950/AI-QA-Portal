# Phase 3, round 9 — one choice, seven starved sections

Review page: <https://claude.ai/code/artifact/f2b75c1c-225b-48c9-8c12-f23e57ce57dc>

Follows [`wip/phase3-omission-mirror.md`](./phase3-omission-mirror.md) (PR #55).

**50 → 44.** Six hits, one cause, one document — and the handover's lead for it was wrong
in a way worth recording, because the tool that falsifies it was already in the repo.

## What the handover said, and what the tool said

`wip/HANDOVER.md` describes this as *"the five-stub block, Sales Tax Act 15.9.2021.
Sections 3B, 4, 5, 6, 7 are stubs at pages 40–43 while 7A, 8, 8A, 8B at pages 39–42 carry
real bodies — the pages **interleave**… Read those source pages before theorising."*

They do not interleave. `tools/acts/why_unbuilt.py` — written for exactly this class, with
a docstring that says *"a stub section is a cascade: one bad resolution advances the `last`
cursor past everything after it, so reading the FIRST failure is the only way to find the
real cause"* — answers it in one run:

```
code       exp found pages     branch            cursor
3           34 [28, 37]        page-anchor tol4    606
3A          39 [31, 33]        NONE                606  all 2 occurrence(s) BEFORE cursor (blocked)
3AA         39 [33]            NONE                606  all 1 occurrence(s) BEFORE cursor (blocked)
3B          40 [31, 34]        NONE                606  all 2 occurrence(s) BEFORE cursor (blocked)
4           40 [34, 37]        NONE                606  all 2 occurrence(s) BEFORE cursor (blocked)
5           41 [35]            NONE                606  all 1 occurrence(s) BEFORE cursor (blocked)
6           41 [35]            NONE                606  all 1 occurrence(s) BEFORE cursor (blocked)
7           43 [37]            NONE                606  all 1 occurrence(s) BEFORE cursor (blocked)
7A          45 [39]            page-anchor tol8    648
```

Read the `found pages` column. Every entry in the block prints about **six pages ahead of
its own contents page** — 3A at 31/33 against an expected 39, 4 at 34 against 40, 7 at 37
against 43. The block is internally consistent; it is the TOC that is off.

Section 3 is the one entry whose code opens **two** body lines: page 28 — its real heading,
six pages ahead, exactly like its neighbours — and page 37, a later cross-reference. And
`build_sections` chose 37.

## Why it chose the wrong one

The page anchor walks a widening tolerance ladder outward from the expected page:

```python
        for tol in (2, 4, 8):
            near = [p for p in positions
                    if abs(body_refs[p].page - expected) <= tol]
            if near:
                pos = min(near, key=lambda p: (abs(body_refs[p].page - expected), p))
                break
```

`|37 − 34| = 3` and `|28 − 34| = 6`. At `tol=2` neither is near; at `tol=4` only 37 is. The
ladder never sees 28 at all — it stops at the first tolerance that hits. **The nearer
candidate is reached before the further one, and here the further one is right.**

The rolling `drift_window` exists for precisely this drift, but it is empty here: sections
1 and 2 never open a body line at all, so section 3 is the first entry to resolve and
`drift` is 0.

Below the ladder sits an ordering guard, and it is worth being precise about why it did not
catch this:

```python
            nxt = next((e for e in ordered[k + 1:] if e.printed_page), None)
            if nxt is not None and body_refs[pos].page > expected_page(nxt) + drift + 8:
                continue
```

It rejects a match past where the next entry is **expected** — 39 + 8 = 47, and 37 is well
inside that. It cannot see where the next entry actually **prints**, which is 31.

## The fix: look ahead one entry, before the ladder rather than after

```python
        if nxt is not None and len(positions) > 1:
            nxt_positions = code_positions.get(nxt.code, ())
            viable = [p for p in positions if any(q > p for q in nxt_positions)]
            if viable:
                positions = viable
```

A candidate that leaves the next entry with no position after it has starved it, and that
is knowable at the moment of the choice rather than seven entries later.

It is a tie-break **between** candidates and never a rejection:

- with one candidate (`len(positions) > 1`) it does not run;
- where every candidate starves the next entry — its code may not open a body line at all,
  which is the ordinary case for an omitted section — `viable` is empty and the ladder
  decides exactly as before.

The one line the ordering guard needed (`nxt`) moved up; nothing else in the pass changed.

## Measured: gained 6, lost 0

Re-converted acts (66/68) and rules (11/12) — the three failures are the Urdu editions,
refused for a family reason, unchanged from Phase 2. The ordinance lane was not
re-converted: `fbr_ingest` has its own builder and does not import `legal_ingest`.

Diffing every document against `output/_pre_r9/`, **exactly one changed**:

| document | leaves | bound | characters |
|---|---|---|---|
| Sales Tax Act 15.9.2021 | 162 → 162 | 151 → 155 | 345,114 → 344,928 |

The −186 characters are the synthesised `"<code>. <heading>"` placeholder strings that five
leaves no longer need. Conservation says so:

```
--- BODY (section/leaf text + table cells) ---   source=49193  conserved=100.000%  missing=0
--- FOOTNOTES ---                                source=11629  conserved=100.000%  missing=0
```

And the block now reads as the statute:

```
  s.3     7929 chars  '3. Scope of tax.– (1) Subject to the provisions of this Act, there shall be ch'
  s.3A      12 chars  '186[3A. ***]'
  s.3AA     13 chars  '187[3AA. ***]'
  s.3B    1099 chars  '189[3B. Collection of excess sales tax etc.– (1) Any person who has collected '
  s.4      784 chars  '4. Zero rating.– Notwithstanding the provisions of section 3 191[except those '
  s.5     1113 chars  '5. Change in the rate of tax.– If there is a change in the rate of tax- (a) a '
  s.6     2256 chars  '6. Time and manner of payment. – (1) The tax in respect of goods imported into'
  s.7     2950 chars  '7. Determination of tax liability. – (1) 210[Subject to the provisions of 211['
  s.7A    1193 chars  '234[7A. Levy and collection of tax on specified goods on value addition. – 235'
```

3A and 3AA stay omissions, which is what the source prints. That document now passes all
58 invariants.

## Two tools that could not do their job

**`why_unbuilt.py` was blind on the rules lane.** It called `calibrate(pdf)` and
`parse_toc(lines)` with no profile, so every RULES document was measured with the Acts
folio, leader, ordinal and codeless-row settings — wrong page offset, wrong TOC row count,
and therefore a cascade reported at the wrong entry. The one diagnostic written for this
class of defect could not be trusted on the lane holding **20 of the remaining 44 hits**.
It now takes `--lane`, resolves `profiles.BY_LABEL`, and passes it the way `pipeline.run`
already does. (Caught while fixing it: `calibrate`'s second positional is `sample`, not
`profile` — the pipeline passes it by keyword.)

**`audit_all.py` had been dying on import.** `scripts/` became `tools/` and this line was
never repointed:

```python
from scripts.convert_all import ACTS, CONSOLIDATED, is_pdf
```

`tools/suite/README.md` names this as the conservation gate to run after every
regeneration, and it has been raising `ModuleNotFoundError` instead. `ACTS` went with the
move — `convert_all` binds its lanes at run time now — so it comes from
`corpus_paths.source_dir("acts")`, which is what that module exists to answer. With it
working, the whole acts lane re-audits clean:

```
customs    20/20 within gate (body >= 99.99%, footnotes 100.0%)
salestax   19/19
excise     17/17
```

## The register

| invariant | acts | rules | ordinance | total | was |
|---|---|---|---|---|---|
| `section_carries_its_body` | **10** | 17 | 5 | **32** | 37 |
| `no_foreign_section_start_in_body` | **1** | 3 | — | **4** | 5 |
| `section_codes_ordered` | 4 | — | — | 4 | 4 |
| `no_chapter_caption_in_section_heading` | 3 | — | — | 3 | 3 |
| `clause_codes_plausible` | 1 | — | — | 1 | 1 |
| **per lane** | **19** | **20** | **5** | **44** | 50 |

## Verified

- `ruff check` bare — clean
- `pytest tools/tests -q` — 58 passed, 1 skipped
- the lock fails with the filter removed (s.3 binds to page 37), passes with it;
  `__pycache__` cleared after
- `discover_corpus.py --check` — no drift; `signatures.json` unchanged
- conservation 100.000% body and footnotes, 56 documents across three families
- documents **80 / 11 / 12**, held · `data/ocr_cache` **0 B**
- rollback: `output/_pre_r9/`

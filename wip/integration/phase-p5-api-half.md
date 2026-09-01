# PR-K — P5's API half: the portal stops deleting and mangling what the pipeline sent

Review page: <https://claude.ai/code/artifact/d7f9baec-c5dd-4697-8029-f9883d46c17e>

Closes the last problem in `plan.md` §3 still marked CARRIED.

Measured on this host, 2026-09-01, from `main` at `31a2f6e` (#74).

---

## 1. What was carried, and what measuring said

`plan.md` P5 named three judgements the API makes that the pipeline's register cannot
see. PR-J gated the pipeline half. The Deferred row for the rest said "guard the
dot-leader pattern against brackets, make the drop a `parse_quality` flag instead of a
delete, and remove the client's live second copy". Re-measured before touching anything:

| the ledger said | measured on the post-PR-J corpus |
|---|---|
| `is_junk_leaf` fires 4 times | **4** — confirmed, and all four are a Customs Act *preamble* (2013–2016) |
| `normalize_heading` rewrites 44 headings in 21 documents | **42 in 21** — PR-J's re-conversion moved it by two |
| "~40 of those 48 are the compensation causing the damage" | stronger than that: **not one of the 42 is TOC chrome.** Eleven parser rounds closed every case the function was written for — no page numbers stripped, no gazette mastheads, no `Section Page No.` columns. All 42 are collateral. |

The 42, exactly:

| × | in | out |
|---|---|---|
| 17 | `Directorate General [...] Internal Audit` | `Directorate General [ ] Internal Audit` |
| 17 | `Directorate General of Valuation [...` | `Directorate General of Valuation [` |
| 4 | `] Tax credit not allowed` | `Tax credit not allowed` |
| 3 | `(REVENUE DIVISION) … INCOME TAX MANUAL` | `(REVENUE DIVISION) INCOME TAX MANUAL` |
| 1 | `] [ ... ] Return` | `[ ] Return` |

`[...]` is not chrome. It is the pipeline's deliberate **"text omitted by amendment"**
marker, emitted with its own `omitted-bracket` class in both builders and preserved by
name in the sanitizer allowlist. A dot-leader run and an omission marker are the same
characters, which is the whole defect.

## 2. The marker had two attackers, not one

The Deferred row named one — the leader substitution. Guarding only that took 42 → 24
and left all 17 truncated cases untouched. The second is four lines further down:

```python
text = _TRAILING_TOC_PAGE_RE.sub("", text).strip(" .·•…")
```

`_TRAILING_TOC_PAGE_RE` needs a digit, so it never matched — but `.strip(" .·•…")` mops
trailing dots unconditionally, and `Directorate General of Valuation [...` ends in
three of them. That is what produced the bare `[`.

Both are now guarded, on the same rule: **an unclosed `[` means those dots are the
marker.** Found by measuring the real function over the corpus rather than the
prototype regex, which passed.

> A note on those 17: the heading arrives from the pipeline **already truncated** — the
> bracket is never closed, while its sibling two leaves away closes correctly. That is
> an upstream defect. This PR stops compounding it and leaves it legible; fixing the
> truncation is a parser round's job.

## 3. Four preambles that never reached a reviewer

All four `is_junk_leaf` victims are the same document in four editions. Recovered from
the scratch database after the change — this is one leaf, verbatim:

```
THE CUSTOMS ACT, 1969
Section Page
No.
224 Extension of time limit. 212
THE FIRST SCHEDULE 216
...
xxi
1[Act No. IV of 1969]
[3rd March,1969]
An Act to consolidate and amend the law relating to Customs
Whereas it is expedient to consolidate and amend the law relating to the levy
and collection of customs-duties 1a[, fee and service charges] ...
It is hereby enacted as follows:-
```

The Contents tail is real, and it is the pipeline's defect —
`inv_preamble_carries_no_toc_tail` counts it, and still does. But the portal's answer
was to delete the node, which took the enacting formula with it: silently, invisibly to
the register, to the conservation audits and to the reviewer.

It is now `toc_tail_in_leaf`, and deliberately **not** in `CRITICAL_FLAGS` — the same
call `page_range_out_of_bounds` already makes. The leaf is readable statute with debris
attached, not a parse failure.

## 4. One deviation from the plan, and why

The plan put `assess_toc_tail` in `parse_quality.py` beside `assess_page_range`. It
cannot go there: three of its four regexes (`_CONTENTS_MARKER_RE`, `_GAZETTE_RE`,
`_GAZETTE_PREFIX_RE`) are shared with `normalize_heading`, and `json_parser` already
imports `parse_quality` — so the move is either a circular import or three regexes
forked across two modules. Forking a regex to fix a forked regex is the wrong trade. It
keeps `assess_page_range`'s `Optional[flag]` shape, in the module where its regexes live.

## 5. Measured end to end, through the real sync

Two real corpus documents — the Customs Act 2014 (the deleted preamble) and Sales Tax
Act 1990 (both omission markers) — driven through `run_sync` into a scratch database,
once with each parser. `wip/integration/measure/p5_seam.py` reproduces it.

```
fresh ingest, old code : 475 sections
fresh ingest, new code : 476 sections

added            1   Customs Act 2014 |/preamble
                     flags=['toc_tail_in_leaf']  status=pending
removed          0
ids re-minted    0   <- nothing else disturbed
status moved     0
headings changed 2   'Directorate General [ ] Internal Audit'
                       -> 'Directorate General [...] Internal Audit'
                     'Directorate General of Valuation ['
                       -> 'Directorate General of Valuation [...'
```

### The thing only running it found: this fix does not travel on its own

Re-syncing the *same* database with the new parser is `skipped 2, 0 rows changed` —
with `--force` too. `create_version` gates on `source_hash`, the JSON **bytes**, and a
change in how those bytes are *interpreted* is invisible to it. That gate is correct and
was designed in deliberately (PR-A: "byte-identical JSON ⇒ no new version, no row
writes"); it simply does not model an API-side parse change.

Two consequences, both worth stating plainly:

- **This PR cannot disturb an existing row.** No production heading changes, no approval
  resets, no version churn on deploy. Measured: 0 of 475.
- **It also does not reach existing rows.** The 4 preambles and the 35 headings arrive
  when those documents are next re-converted — which the 14 stale acts documents and the
  next parser round will do anyway. This is PR #37's *"the fix never travelled"* in a new
  guise, and it belongs in the ledger rather than being worked around here: forcing a
  re-parse of the whole corpus to pick up a heading change is a decision with its own
  evidence, not a side effect of this PR.

## 6. Gates verified to fail on purpose

*A gate that cannot fail is a no-op.* Each stubbed out, `__pycache__` cleared, re-run:

| stub | fails |
|---|---|
| revert both bracket guards | `test_the_omission_marker_survives_heading_normalisation` |
| restore the early-return deletion | `test_flags_gazette_and_contents_leaves_and_normalizes_headings`, `test_a_preamble_with_a_contents_tail_is_flagged_not_deleted` |
| `git checkout` `tocLabels.js` (cleanHeading back) | `renders the API heading verbatim, including the omission marker` |

## 7. The register moved by zero

This is an API change; the pipeline defect is still the pipeline's.

| | acts | rules | ordinance | total |
|---|---|---|---|---|
| before | 20 | 9 | 5 | **34** |
| after | 20 | 9 | 5 | **34** |

`register.json` is byte-identical, `EXPECTED_COUNTS` unchanged at 61/61/47, and
`inv_preamble_carries_no_toc_tail` still reports its 4 hits — the cause did not go away
because the symptom did.

## 8. What ran

```
598 passed, 1 skipped, 0 failed      apps/api/backend/tests + tools/tests
ruff check                            All checks passed  (bare, matches ci.yml)
oxlint --deny-warnings                clean
vitest tocLabels + qualityFlags       24 passed
run_suite acts / rules / ordinance    ALL PASS  61/61 · 61/61 · 47/47
```

The full vitest suite is not a gate on this host — 17 of 191 fail identically on clean
`main` because Node 26 needs `--localstorage-file` (`tasks.md`, 2026-08-31). Per-file
runs are what PR-C used; the suite is CI's job.

## 9. Net

| | before | after |
|---|---|---|
| headings rewritten at ingest | 42 | **7** |
| omission markers destroyed | 35 | **0** |
| leaves silently deleted | 4 | **0** |
| leaves flagged instead | 0 | **4** |
| heading normalisers | 2 (API + client fork) | **1** |
| `tocLabels.js` | 213 lines | **172** |

The 7 remaining rewrites are the 4 leading-`]` strips and 3 stray ellipses — harmless,
and both are really the pipeline's to stop emitting. `normalize_heading` was left in
place rather than deleted for exactly that reason: with zero true positives it has no
job left, but deleting it today would put `] Tax credit not allowed` on a reviewer's
screen. That is a parser round away, not an API change.

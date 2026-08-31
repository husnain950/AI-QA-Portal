# Phase 3, round 8 — a repealed section has nothing left to steal

Review page: <https://claude.ai/code/artifact/dc57e677-ef8e-44ad-822e-2595ccd2c2ac>

Follows [`wip/phase3-gate-the-register.md`](./phase3-gate-the-register.md) (PR #53).

**64 → 50.** No parser change, and no document was re-converted: the JSON on disk is
byte-identical before and after. Ten hits were the invariant reading its own twin's rule
differently; four were a mirror that was never written down.

## 1. The pair disagreed about what "starved" means

`section_carries_its_body` and `no_foreign_section_start_in_body` are documented as two
halves of one report — *"that one names the starved section, this one names the leaf that
ate it, and the pair is what makes a misattribution diagnosable rather than merely
visible."*

The first one skips omitted sections. It has since it was written
(`_common.py:1180`), and the reason is in its docstring: a repealed section is
*legitimately* empty, so an empty one is not evidence of anything.

The second one never asked. It tested the victim with `_body_beyond_heading(victim)` alone,
which is `""` for a repealed section for the same reason it is `""` for a starved one. So
one half of the pair reported ten hits the other half had already dismissed.

What that looks like on the document — the Customs Act, seven consecutive editions:

```
section 2:  ... such other 20[officers of Customs as may be notified by the Board;]
section 20: 15[20. 112[Omitted]
```

The `20` in section 2 is an **amendment marker**, not a section code. The permissive
`_ANY_SECTION_START` is meant to see it — its looseness is deliberate, and the five
surrounding conditions are what filter it out. Condition four is the one that should have:
"the victim leaf carries no body of its own, which is the signature of the binding
failure". Section 20 carries no body because Parliament omitted it in 2005. Nothing was
eaten.

The same shape in three more places:

| document | victim | its whole `plain_text` |
|---|---|---|
| Customs Act ×7 editions (2019 → 2025) | s.20 | `15[20. 112[Omitted]` |
| Sales Tax Act 15.9.2021 | s.3A | `Omitted` |
| Sales Tax Act 2014 | s.42 | `10[ 42. *** ]` |
| Sales Tax Rules 30-06-2025 | s.14A | `14A. [omitted]` |

The fix is the guard the twin already has, reusing the same predicate:

```python
            if _is_omission(victim):
                continue          # legitimately empty: nothing was there to eat
```

**Measured on identical JSON: 64 → 54.** Both halves of the pair now agree, and the
invariant is not weakened — the second assertion in the lock is a victim that is merely
heading-only, which must still be reported.

### It made one hit more honest rather than fewer

The invariant reports at most one hit per leaf and then breaks. On Sales Tax 15.9.2021 the
first match in section 2's body was the omitted `3A`; with that skipped, the scan continues
and finds `189[3B. Collection of ex…` — section 3B, which is a **real** starved leaf and
one of the five in that document's stub block. The hit count for that document did not
change. What it points at did.

## 2. A mirror that was never written down

Round 3 exempted `section_carries_its_body` on the two compilations — Customs Rules 2001
(44 index rows) and Federal Excise Rules 2005 (a second instrument starting at PDF page
75) — on evidence traced to the source PDF, with the deletion of those entries as the
Phase 5 gate.

The mirror invariant fires on the same two documents, from the same cause, and was never
exempted:

```
Customs Rules 2001   rule 3  body holds  '7. Jurisdiction _____________________'
                     rule 5  body holds  '6 Annexure-E.2 Legal Compliance YES YES YES'
                     rule 1  body holds  '15.06.2002.'
Federal Excise 2005  rule 1  body holds  '2. Definitions.--1n these Rules, unless ...'
```

Every victim is one of the index-row or contents-row leaves already covered above. The
pipeline cannot express these documents either way, and the pair must agree — so the two
entries are added with the same traced evidence and the same deletion condition.

**54 → 50.** The exempted hits still run and are still printed with their counts; an
exemption documents a failure, it does not hide its size.

`wip/tasks.md`'s Phase 5 gate said "four entries" and then enumerated three. It is now
five, and counted.

## 3. `register.json` has a generator

Seven rounds hand-copied the `FAIL (n)` counts into `tools/suite/register.json`, and a
mis-copy would have gated the wrong number in the very PR that moved it.
`test_register_snapshot.py` already had `_measure()` producing exactly that shape, so the
generator is the test read backwards:

```sh
python tools/tests/test_register_snapshot.py --write
```

`_comment` is preserved — it is the file's rationale, not data.

## The register

| invariant | acts | rules | ordinance | total | was |
|---|---|---|---|---|---|
| `section_carries_its_body` | 15 | 17 | 5 | **37** | 37 |
| `no_foreign_section_start_in_body` | 2 | 3 | — | **5** | 19 |
| `section_codes_ordered` | 4 | — | — | 4 | 4 |
| `no_chapter_caption_in_section_heading` | 3 | — | — | 3 | 3 |
| `clause_codes_plausible` | 1 | — | — | 1 | 1 |
| **per lane** | **25** | **20** | **5** | **50** | 64 |

The five survivors of the mirror invariant are all real, and all already have a round:

- Sales Tax 15.9.2021 s.3B — the cursor cascade (round 9)
- Sales Tax 30.06.2021 s.30 — a TOC row bound as a body (round 11)
- Sales Tax Rules 01-01-2025 ×3 — footnote text read as a section start (round 10)

## Verified

- `ruff check` bare — clean
- `pytest tools/tests -q` — 56 passed, 1 skipped
- `discover_corpus.py --check` — no drift
- `data/ocr_cache` — 0 B
- `git status data/` — empty; no document was re-converted, so conservation is unchanged
  by construction
- the lock fails with the guard removed, and `__pycache__` was cleared afterwards

`run_tests_smoke.py` still exits non-zero: the register is 50, not 0. Expected, and
pre-existing.

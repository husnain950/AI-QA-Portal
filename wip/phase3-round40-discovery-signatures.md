# Round 40 — `discover_corpus --check` was stale, and it was one character

**Row q3.** The pipeline gate's only red. `tools/discover_corpus.py --check` exited 1 on
`main` with a list of 27 documents, and had done since **PR #86 (round 20)**. This round
regenerates the artifacts and attributes the drift. **No production code changes** —
`packages/` is untouched.

## What was red

```
$ .venv/bin/python tools/discover_corpus.py --check       # on main, cb11b49
drift: signatures.json is stale, rerun --write and review the diff
  CHANGED  Customs Act, 1969/ Customs Act ,1969 (Amended upto 30th June 2007).pdf
  … 27 lines, all CHANGED
exit 1
```

**27 `CHANGED`, zero `NEW`, zero `GONE`, zero `MOVED`.** No document entered or left the
corpus and **no family assignment moved**, so nothing the classifier decides was affected.

## The attribution

Every one of the 27 records differs in **exactly one field**, `signature.chapter_lines`:

```
  27  signature.chapter_lines
```

`signatures.json` was last written at **`f7269d8`** (round 6, PR #51, 2026-08-30).
`grammar.CHAPTER_RE` last moved at **`2d6fa52`** (PR #86, round 20). The difference between
those two revisions is one character in the separator class:

```python
-    rf"^\s*\[?\s*{spaced('CHAPTER')}[\s\-]+({NUMERAL})"
+    rf"^\s*\[?\s*{spaced('CHAPTER')}[\s\-–]+({NUMERAL})"
```

That is round 20's **CHAPTER en-dash** widening — the second gap round 18 located on the
same line of code and left open on evidence. `signature.measure` counts `CHAPTER_RE`
matches into `chapter_lines`, so widening the parser silently moved a discovery signature
that no round regenerated.

**Proved, not inferred.** Restoring the pre-#86 regex in-process and re-running the census
reproduces the committed `signatures.json` **byte-identically**:

```
byte-identical to signatures.json with the OLD regex: True
```

So the whole 27-document drift is that one character, and nothing else has drifted since
round 6.

## The diff reviewed

| | before | after |
|---|---|---|
| documents | 190 | 190 |
| families | 117 consolidated / 36 amending / 30 no_text_layer / 4 urdu / 3 unconvertible | **unchanged** |
| records differing | — | 27, all `chapter_lines` |
| `signatures.json` | | 27 lines changed |
| `report.md` | | 27 lines changed, all the §4 `CH` column |

Two shapes in the delta, and every gained line was read:

- **+2 on 24 documents** — 20 Customs Act editions, 2 Income Tax Rules, 1 Sales Tax Rules.
  e.g. Customs Act 30th June 2008 gains `CHAPTER – VI` and `CHAPTER – VII`, separator
  `U+2013`.
- **+15, +15, +15, +8 on four Income Tax Rules 2002 editions.** The 18-10-2016 edition
  gains `CHAPTER – IV` once and `CHAPTER – XV` **fourteen times** — a running page head
  repeated through chapter XV, not fourteen chapters.

Every gained line matches `^\s*\[?\s*CHAPTER\s*–\s*<numeral>$` with a real U+2013. There
are no false gains. The repeated `CHAPTER – XV` is **correct for this metric**:
`chapter_lines` counts *lines*, and `families.py` reads it as a floor
(`chapter_lines=40`) meaning "this document prints chapter structure", not as a chapter
census. It is why no family moved.

## The gate

No new gate. `run_tests_smoke.py:125` already runs `--check` as a regression, and it is the
check that was failing. **Pre-round tree: exit 1 on 27 documents. Post-round tree: "no
drift".** That is the mutation test — the gate can be made to fail on purpose by checking
out `main`.

```
$ .venv/bin/python tools/discover_corpus.py --check      # no drift          (was exit 1)
$ .venv/bin/python tools/discover_corpus.py --assert     # 190 documents, 0 problems
$ .venv/bin/python tools/run_tests_smoke.py              # Pipeline gate passed
    OK tools/discover_corpus.py --check: 1 edition(s) pass
    OK tools/run_suite.py ordinance: 12 edition(s) pass
    OK tools/run_suite.py acts:       80 edition(s) pass
    OK tools/run_suite.py rules:      11 edition(s) pass
$ .venv/bin/python -m pytest tools/tests -q              # 310 passed, 1 skipped
$ .venv/bin/ruff check                                   # All checks passed!
```

## What this round did not do

- **No parser change.** `packages/` is byte-identical to `main`. No document was
  re-converted and no `output/*.json` moved; a discovery signature is measured from the
  **source PDF**, not from the corpus output.
- **Did not add a CI gate.** `data/corpora/*/output/` is gitignored, so this check SKIPs on
  CI exactly as the lane suites do. That is the standing limitation in
  `working-rules.md` → *"CI does not gate the pipeline"*, not something this round
  introduced or can close.
- **Did not touch `unexplained.json`.** `--assert` reports 0 problems; nothing needed
  exempting.

## What it leaves behind

A general lesson worth the ledger: **a parser widening can move a discovery artifact, and
the artifact will not say so.** `chapter_lines` sat 27 documents wrong for twenty rounds
because the only thing watching it is a gate that CI skips. Any future round that touches
`CHAPTER_RE`, `PART_RE`, `DIVISION_RE`, `SCHEDULE_RE`, `TABLE_RE` or the TOC row patterns
should rerun `--write` in the same round — `signature.measure` reads all of them.

# How to work on this

The rules below were each paid for. `wip/tasks.md` says of the original set that they are
*"the part that has not aged"* — they are carried here with the ones rounds 12–14 and the
integration track added since.

State is in [`README.md`](README.md); the work itself is in [`open-work.md`](open-work.md).

---

## Conversion

**Never edit `packages/` while a conversion runs.** `convert_all.py` spawns a fresh child
per document, so each imports the parser *when it starts*; an edit mid-run gives early
documents the old code and later ones the new. **A mixed-revision corpus looks completely
normal.** This was done twice in one session, costing ~30 minutes. Kill and restart.

**`convert-all` converts the whole *lane*, not the corpus.** `make convert-all
LANE=ordinance` targets all 46 ordinance PDFs where only 12 are in the corpus — running the
documented "re-convert the lane" command would have quadrupled it and pushed 34 new
documents at the portal. Convert per file with an explicit `-o`. **The same gap exists on
acts** (80 of 93).

**`convert_all.py` cannot resume.** Two runs were killed mid-flight in one round, leaving 49
of 80 acts documents at the new revision — exactly the mixed-revision hazard above.
`--skip-existing` does not help: after a re-conversion every output exists. What worked was
converting only outputs older than the parser's mtime.

**Nineteen source files have no `.pdf` extension**, not two. This rule used to name only
Customs Rules 2001 and The Finance (Supplementary) Act 2022; a round-16 walk of the three
lanes counts **6 in acts, 12 in rules, 1 in ordinance** — five Customs Act editions, four
Sales Tax Rules 2006 editions, seven Recruitment Rules SROs among them. A `**/*.pdf` glob
misses every one **silently**, and so does the obvious repair
`name.endswith(".pdf") or "." not in name`: these names carry a dot in their *date*
(`Customs Act, 1969 as amended up to 30.06.2021`). Sniff the file or list the directory —
do not pattern-match the name.

**`make convert-*` from a worktree runs the wrong interpreter.** The Makefile takes
`PYTHON := $(ROOT)/.venv/bin/python` only when that file exists, and `ROOT` is the
*worktree*, which has no `.venv` — so it falls back to `python3` and dies on
`ModuleNotFoundError: No module named 'pdfplumber'`. Pass the main tree's interpreter:
`make convert-rules PYTHON=/Users/muhammad.husnain/Downloads/code/crx/.venv/bin/python
PDF="…" OUT="…"`. `PYTHONPATH` off the same `ROOT` is correct as-is — it must point at the
worktree's `packages/`, which is the whole reason to convert from there.

**Know which tree you are editing, and give the worktree the corpus.** `data/corpora/*`
is gitignored, so a fresh worktree holds only `data/corpora/README.md` — and every
`tools/*.py` derives **both** the import root and the corpus root from `__file__`. So
running them from the main tree measures **main's** parser, and running them from the
worktree finds **no documents**. Symlink the lanes in once, per worktree:

```sh
for L in acts rules ordinance; do ln -sfn "$PWD/data/corpora/$L" .worktrees/rN/data/corpora/$L; done
```

(Use absolute targets — a relative `../../../` from `.worktrees/rN/data/corpora/` lands in
`.worktrees/`, not the repo root, and resolves to nothing.) Related, and it cost real time
in round 15: **the Bash tool's cwd resets between calls**, so a `python - <<PY` heredoc
using a *relative* path silently patched `packages/` in the **main tree** instead of the
worktree. Half the round's changes landed on the wrong branch. Use absolute paths in
every edit, and `git status` in **both** trees before you trust a measurement.

**Clear `__pycache__` after any mutate-and-restore verification.** Patching a module,
re-importing and restoring leaves stale bytecode: the source is right while the module in
memory is the version you rejected. This was caught by pytest only *after* a re-conversion
had already run against it.

## Measuring

**Measure the invariant fix and the parser fix separately**, on identical JSON for the
first. Nearly every class is part wrong-invariant and part real defect, and a single total
hides both. `no_footnote_text_in_body` was 45 hits that were *all* a `title=` attribute —
concealing a 473-footnote defect underneath.

**Measure candidate widenings as gained/lost — and know which corpus you are measuring.** A
naive `MARKER_PREFIX` widening scored **1 fix : 17 false positives**; the narrowed form
scored **1 : 0**. But every measurement here runs over `output/*.json` `plain_text`, and
**that is not what the parser sees**: the parser's line is `42 53 [202B.` where the
rendering collapses it to `42 53[202B.`. A lookahead anchored on `[` matched the JSON and
missed the PDF.

**Verify a lock by removing the fix.** A parenting lock passed with the fix stubbed out —
its two-chapter fixture let a later pass repair the damage. Three chapters reproduced the
real document. **A gate that cannot be made to fail on purpose is not a gate.**

**A row's predicted cause is not evidence, however confidently the ledger states it.**
`plan.md` P3-6 said `section_codes_ordered` was "the code was misread" and ranked the row
as three PDF pages to read. Reading them disproved the premise: **no code was misread** —
three *chapters* were mislabelled, and the invariant only ever saw the consequence. The
row also predicted `exemptions/acts.json` would be needed; it was not, and still does not
exist. Two rows still open carry a predicted cause in the same voice (P3-1a, P3-1c, "each
already traced to a printed defect") and **neither has been checked against a page since
it was written**. Read the page first; the ledger's guess is a hypothesis.

**Report changes that moved a number by zero.** Round 4's acts lane and round 6's PART fix
were both correct and both scored nothing; folding them into a total would have
misattributed the rounds that did move it. **Round 17 is a whole round of this**: the
container-code guard fixed 14 real boundaries and left the register at 25, because no
invariant can see a swallowed `PART-N`. Its evidence is a gained/lost diff, not the
register.

**A conservation number that goes UP can be a duplication.** The audit
(`tools/acts/audit_completeness.py`) compares word *multisets*, so it scores presence, not
placement — and a line held in two leaves at once counts as conserved. Round 17 measured a
candidate CHAPTER guard at 74.087% → **74.099%** on Customs Rules 2001 and all 28
"recovered" tokens were the preamble swallowing rule 1's opening text a second time. **Not
one leaf changed.** This is the companion to round 13's warning that a sliced form stays at
100.000%: conservation is blind in *both* directions, so pair it with a line-level diff of
which leaf holds what. Neither number is evidence on its own.

**A cached artifact cannot tell you its generator is wrong.** Three instances in one phase:
a `known_gaps` skip inside a check function, two `exemptions/` entries, and `report.md` §5 —
wrong from PR #45 to PR #51 because it had not been regenerated since Phase 0. Only the
`exemptions/` format reported itself stale, unprompted. That is the argument for the
register snapshot.

**Read the comments before generalising.** `_DOTSUFFIX_RE` carried a measurement saying its
bracket gate was safe. Re-running it showed the measurement had expired — but it was still
right about the danger.

**The obvious generalisation is often wrong.** `XIVA` and `XIV-A` are two *different*
chapters of Sales Tax Rules 2006; matching numerals by value collapses them.

## The seam to the portal

**A parse-only change does not travel.** `create_version` gates on `source_hash` — the JSON
*bytes* — so editing `json_parser` / `parse_quality` / `html_sanitizer` reaches no existing
row on re-sync, **`--force` included**. Measure it as two fresh first-ingests into a scratch
database (`wip/integration/measure/p5_seam.py`), never as a re-sync of an existing one.

**The local dev database is many rounds stale.** An acts document that was never
re-converted and never re-synced has **304 of 309** stored leaves differing from a fresh
parse. Any carryover or approval-loss number measured against it is an artefact of its age,
not of the change under test.

**Run the whole web suite, against its baseline.** `npx vitest run` is **17 failed here,
always**, in `libraryFavorites` and `libraryPage` (Node 26 wants `--localstorage-file`; CI
pins 22). Diff against that baseline — do not skip the suite, and do not run only the files
you touched: that misses the ones that *consume* them, which is how #75 shipped a red build.

**The Northflank deploy is outward-facing and gated on green CI on `main`.** Confirm before
triggering it.

## Gates and lint

**CI does not gate the pipeline.** `data/corpora/*/output/` is gitignored, so
`run_tests_smoke.py` SKIPs all three lane suites on CI. Seven rounds moved the register
210 → 64 with nothing enforcing those numbers but prose and a human reading it. Green checks
on a PR are **not** evidence about ingest. `tools/tests/test_register_snapshot.py` is the
real gate, and it only runs where the corpus is staged.

**Run `ruff check` bare.** `pyproject.toml`'s `src = ["apps/api", "packages", "tools"]` is
what pulls `packages/` in; `ruff check apps/api tools` silently misses it. The Makefile and
`ci.yml` both run it bare — match them.

**A regression case should assert the property it names, not the markup.** Two cases were
pinned to an attribute-free `<p>` that the current parser classes; `re.search` made the fix
two characters each. A case naming a structural property must match that property, or it
fails the next time the renderer improves.

## Constraints a fix must not violate

- **`detect_toc_pages`'s `rows >= 3` floor.** Its own comment records a lower one swallowing
  the Income Tax Rules' body title page.
- **`clause_codes_plausible`.** Do not weaken it to clear its one hit.
- **`test_the_letter_suffixed_chapter_gap_is_still_open`** asserts the current *wrong*
  answer on purpose. Its failure is the signal that the CHAPTER-suffix widening landed — not
  a test to repair.
- **`data/ocr_cache` stays 0 B** until OCR is deliberately taken in scope. Taking it in scope
  wakes the fidelity-floor invariants and routes sub-floor scans to `_provisional/`, which
  removes them from the portal.
- **`grammar.ROMAN_FOLIO_RE` is bounded at `ccxcix` and lowercase on purpose** — `mix` is
  both a valid roman numeral (1009) and an ordinary English word.

## And the one that governs all of it

**Fixed, or exempted with evidence traced to the source PDF. There is no third state.**
"Tracked and deferred" without an entry in `tools/suite/exemptions/<lane>.json` is a red
gate, not a decision.

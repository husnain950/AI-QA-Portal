# How to work on this

The rules below were each paid for. `wip/tasks.md` says of the original set that they are
*"the part that has not aged"* — they are carried here with the ones rounds 12–14 and the
integration track added since.

State is in [`README.md`](README.md); the work itself is in [`open-work.md`](open-work.md).

**One rule below changed state on 2026-09-10.** The corpus is no longer mixed-revision for
acts and rules: the round-27 re-conversion put all **77** of those documents at `f3a37e0`,
and `test_register_snapshot.py` now passes on this machine with nothing stashed. The
mixed-revision rules still apply to the **ordinance** lane (12 documents at round 12) and the
14 acts documents rounds 21-28 deliberately skipped — and they apply again the moment
anyone converts a subset. Do not read the all-clear as permanent.

---

## Conversion

- **Convert from a CLEAN tree, or the provenance stamp is worthless.**
  `legal_contract.pipeline_revision` appends `-dirty` when the tree has uncommitted changes,
  and it records the tree's HEAD, not the change you are testing. Converting 77 documents from
  a worktree with the round's edits still uncommitted stamped them
  `8032b142c72f-dirty` — the commit *before* the fix, marked unanswerable. Commit first, then
  convert, then measure. Done once on 2026-09-14 and it cost a second 16-minute run.

- **Re-convert the STAGED SET, never the lane.** `convert_all.py <lane>` discovers every PDF
  under the lane — 46 ordinance + 93 acts + 48 rules = **187**, against **103** staged
  outputs. A bare run adds 84 documents to the corpus, and the register then measures a
  different document set: a before/after comparison stops meaning anything. Filter
  `discover()` to paths whose `out_path()` already exists. Measured 2026-09-14.
- **Three ordinance outputs carry a legacy filename.** `Income Tax Ordinance 2001 - amended
  upto 30.06.2024.json` is on disk; `out_path` now writes `Income Tax Ordinance, 2001 Amended
  upto 30.06.2024.json`. Converting them under `out_path` leaves the old file in place and the
  lane holds **15** documents, three of them duplicates. Pass `-o` with the name already
  there. (They are image-backed, so a no-OCR run skips them and never trips this — it fires
  the moment OCR comes into scope.)

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

**Or skip the symlinks: only the IMPORT root comes from `__file__`.** The corpus root goes
through `corpus_paths.get(lane).path()`, which honours `CORPUS_ACTS` / `CORPUS_RULES` /
`CORPUS_ORDINANCE` — that is the whole point of those variables and `corpus_paths._demo`
asserts it. So `CORPUS_ACTS=$MAIN/data/corpora/acts … $MAIN/.venv/bin/python <run from the
worktree>` gives the worktree's parser the main tree's corpus with nothing on disk to undo,
and a lane you forget to pass resolves to the worktree's empty one and reports **0
documents** rather than quietly measuring `main`. Round 46 converted all 77 that way.

(Use absolute targets — a relative `../../../` from `.worktrees/rN/data/corpora/` lands in
`.worktrees/`, not the repo root, and resolves to nothing.) Related, and it cost real time
in round 15: **the Bash tool's cwd resets between calls**, so a `python - <<PY` heredoc
using a *relative* path silently patched `packages/` in the **main tree** instead of the
worktree. Half the round's changes landed on the wrong branch. Use absolute paths in
every edit, and `git status` in **both** trees before you trust a measurement.

**Installing the output is part of the round, and nothing checks that you did.** Round 39
measured its table fix by converting 119 documents twice and never copied the post-change
output into `output/`, so for a day the corpus served round 38's rendering from a tree whose
code contained round 39's fix. The QA tracker recorded FS-02 and FS-07 as open, and it was
RIGHT about the portal and wrong about the code. Nothing catches this: the lane suites and the
register read whatever is on disk, so a stale-but-self-consistent corpus is green. After a
round that changes any document, check `metadata.pipeline_revision` on that document, not just
the diff you measured. **Shipped, measured, and installed are three states, not two.**

**Two rounds shipped code that moved nothing, because the documents carrying the hits were
not staged.** Rounds 20's fixes for the heading-terminator scan, the omission spellings,
`preamble_carries_no_toc_tail` and `clause_codes_plausible` were all correct and all
measured zero, and the ledger carried the four rows as open for a full round. **A fix that
is shipped and a fix that is measured are two different states** — say which one a round
reached, and never write a Result that implies the second when only the first happened.

**Snapshot `output/_pre_<round>/` BEFORE the first conversion of the round, and never copy
into it again.** Round 37 snapshotted one document, converted it, then later ran
`cp output/*.json output/_pre_37/` to cover the rest of the lane — which overwrote that
document's baseline with the *post-change* output, and the first corpus diff reported the
round as a 2-citation change. The recovery is the right move if it happens: add a worktree at
the pre-round commit, symlink the corpora in, and run **the worktree's** `tools/convert.py`
with **the main tree's** interpreter (`$MAIN/.venv/bin/python $WT/tools/convert.py …`) —
`__file__` then resolves imports to the worktree's `packages/` and the corpus to the symlinks.
That regenerates a true baseline in one conversion, and it is better evidence than a stored
output anyway: it is the same document through `main`'s parser today.

**`data/corpora/_reconvert/run.py` spends ~7 minutes doing nothing visible before the acts
lane starts.** `convert_all.scan_page_count` is an exact per-page census and it opens all 93
acts PDFs — including the 14 image-backed ones, 2,065 pages — before the first child process
spawns. A run sitting at "11 rows" in the ledger for seven minutes is **normal**, not hung.
Whole run: 77 documents, 4 workers, **953s**.

**Clear `__pycache__` after any mutate-and-restore verification.** Patching a module,
re-importing and restoring leaves stale bytecode: the source is right while the module in
memory is the version you rejected. This was caught by pytest only *after* a re-conversion
had already run against it.

## Gates

**`applies_to` must name the EDITION, not a date.** Round 38 scoped 17 acts cases to
`"30-06-2025"` — which also matches `Sales Tax Act 1990 amended upto 30-06-2025`, so
three of them ran against the wrong document and the lane went red on a document the
round never touched. Two acts editions share that date and more share others. Use the
filename as far as it is distinctive: `"Federal Excise Act, 2005 as amended upto
30-06-2025"`.

**Run every new gate against the PRE-ROUND output before believing it.** Three of round
38's seventeen cases passed on the broken document, i.e. they were no-ops, and each
failed for a different reason worth knowing:

- **`.` does not cross a newline.** A pattern spanning from one clause to the next
  (`\(c\)(?:(?!</li>).)*\(d\)`) never matches, because the clauses are on separate
  lines — and a `*_not_matches` check then *passes* on exactly the markup it was
  written to forbid. Use `[\s\S]`, or pass `re.DOTALL`.
- **`plain_text` keeps the raw marker digit**, so `against S. No. 9` reads identically
  whether or not the 9 became a citation. A citation is only visible in the html.
- **A lookahead ends a match before the thing you wanted to read.**
  `</p>(.*?)(?=<p|<ol)` captures the whitespace *between* two blocks, not the next
  block's text, so an invariant written that way can never fire.

The cheapest check is `run_suite.py <lane> <path-to-_pre_N/<doc>.json>`: a case that
passes there is not a gate. Round 38's four invariants and fourteen of its cases fail
there and pass after; the one case that passes both ways is a deliberate pin.

**A re-conversion with 4 workers can be OOM-killed on this machine.** Round 38's second
pass died mid-flight; `data/corpora/_reconvert/run.py` is resumable from its ledger, so
the restart only redid what was in flight — but drop `max_workers` to 2 and expect the
acts `scan_page_count` phase to take 10-13 minutes before the first child spawns.

## Measuring

- **A marker-grammar change is invisible to the register, to CI and to the lane suites.**
  Round 35 widened `grammar.MARKER` and lifted **56 section cross-references into `<sup>`** in
  a document the round was not about (`72A` ×30, out of "by virtue of section 72A of the Sales
  Tax Act, 1990"). The register read **0 before and 0 after** — the invariants share the
  parser's marker grammar, so they are blind to exactly the population a marker change moves.
  **Read the rendered `html` of a document the round is NOT about**, and diff it against the
  same document on `main`. That is the only thing that caught it.
- **An invariant with nothing to measure is not passing — it is unmeasured.** Customs Rules
  2001 carried **zero** footnote records, so all nine footnote invariants were green on it for
  the life of the corpus: there was nothing for them to look at. Round 37 gave it its first
  421 records and `footnote_on_citing_leaf` reported a defect **on the same run** — a gridless
  table span that had been swallowing a CHAPTER caption the whole time. Budget for this: a
  round that gives a document its first record of some class should expect the suite to have
  something to say about that document, and the hit is usually older than the round.
- **A document that records zero of something is a lead, not a clean bill.** The census that
  found round 37 was *markers with no notes*; the two documents at the top of it had 665 and
  869 markers and **0** notes each, and one turned out to print its apparatus in a place no
  gate looked. Zero is the strongest signal in this corpus.
- **`marker_max_size` is `body_size - 1.5`, which is not a marker band.** It is 10.5 where
  body is 12.0, so it admits footnote prose whole. If a rule needs "this word is a raised
  marker", test against `footnote_size` and check `footnote_marker_max_size > 0` first — a
  document with no footnote zone calibrates `footnote_size` to nonsense (11.0 for Sales Tax
  Rules 01-01-2025, whose real footnote prose is 9.0 and which has 0 footnote records).

**A zone that a document does not have is not the same as a zone it should not have.**
`calibrate` gives up (`zone_mode "none"`) when the two commonest prose sizes are within
`SIZE_GAP_MIN`, and that is right when they are two BODY sizes -- but the give-up is applied
to the DOCUMENT when the evidence is only about the CANDIDATE. Round 41 paid this: Sales Tax
Rules 2006 (01-01-2025) prints two whole pages at 11.0pt against a 12.0pt body, so 11.0 won
the second slot and 869 markers had nowhere to resolve. **And the repair has a failure
direction of its own**: promoting the next candidate on mass alone gave Finance Act 2024 a
zone made of SCHEDULE TARIFF ROWS -- 10 false records reading `S. No. Taxable Income Rate of
Tax`. Finance Act 2019 already ships 95 of those. **Before believing a new footnote zone,
check WHERE the candidate's words sit on the page**, not just how many there are.

**A promotion guard is not a demotion rule.** Round 41 earned the test "at least half of
this size's words sit in the bottom 40% of the page" and used it to decide whether a
CANDIDATE footnote size may be promoted. Round 44 measured turning the same test around --
does this document deserve the zone it has? -- and it demotes **38 documents, 26 of them
staged, including every Customs Act edition at 31-44%**, because Customs prints its notes on
whole COLLECTOR PAGES after each body run, where there is no body text for them to sit below.
A per-page variant ("the footnote text starts below where the body text ends") is no better:
it demotes 9 staged documents whose records are 92-100% real notes, because a dense apparatus
continues from the previous page and therefore starts at the top. **A test that is sound in
one direction can be destructive in the other; measure the reversal before reusing it.**

**A clean size split can still be wrong about what it separates.** Finance Act 2019 sets its
schedule tariff tables at 8.0pt against an 11.0pt body, so `calibrate` finds a textbook
body/footnote pair and everything under the cut is TABLE: 95 footnote records, 5 bound, none
reading like a note. **Ask the zone what it holds**, with
`pagemodel._is_amendment_note` -- whose own docstring already carried the measurement
("97.7% of real footnotes match; a body rate/penalty TABLE cell never does"). And put a
SAMPLE FLOOR on the question: Customs Rules 2001's size zone holds 24 lines and no notes
because its apparatus is printed once at the end at body size, and it carries 419 real
records. A thin zone is not evidence of absence.

**A duplicate record moves no words.** Round 44's 95 false records each carried a `text` and
an `html` copy of text that ALSO remained in the body, so removing them dropped 2,122 words
from the file and changed the body by nothing -- `Cocoa powder` went 9 occurrences to 2, and 2
is the floor (the leaf's `plain_text` plus its `html`). Count a probe's occurrences, not the
total: the total falls in exactly the way a real loss would.

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

**A leading QUOTE is not decoration, however much it looks like one.** Round 42 measured
admitting `“` before a container caption, because Customs Rules 2001 prints
`“Chapter XX` as a substituted heading. The same glyph opens QUOTED REPEALED TEXT, and
that is the commoner reading: Customs Act 1969 p219 prints `“Chapter XIX-A` under *"At
the time of omission section 196-K to 196-U were as under:"* while the LIVE chapter is
already cut sixteen lines above. Accepting it mints a duplicate chapter and re-parents
eleven repealed sections as law in at least twenty editions. `suite/invariants/_common.py`
had the answer already, in `_QUOTE_CUE`.

**A census over `extract_text` cannot see a superscript.** Round 42's first boundary census
screened every corpus line through `signature.extract_text` and reported the marker-run class
as **zero gains** -- because that extractor hands `2&30 [CHAPTER XIV` over as `[CHAPTER XIV`,
which the narrow regex already accepted. The class it was written to measure was invisible to
it. Re-run over `calibrate._page_lines`, the parser's own line text, it is there. This is the
same rule as *"measure against the parser's line text, not the rendered output"*, and it now
has a second instance.

**Do not monkeypatch a module global inside a process pool to A/B a regex.** The same round's
pooled census reported 3 gains where a direct call on one document returned 3 for that
document alone. Pass the pattern into a local reimplementation of the three-line predicate
instead; it is thread-safe, it is faster, and it cannot silently measure the wrong arm.

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

**A parser widening moves the DISCOVERY artifacts, silently.** `signature.measure` counts
`CHAPTER_RE`, `PART_RE`, `DIVISION_RE`, `SCHEDULE_RE`, `TABLE_RE` and the TOC row patterns
into the signature it writes to `tools/discovery/signatures.json`. Round 20 added the
en-dash to `CHAPTER_RE`'s separator class and moved `chapter_lines` on **27 documents**; the
artifact stayed stale for twenty rounds, because the only thing watching it is
`discover_corpus.py --check` — a gate CI skips. Touch any of those patterns and rerun
`--write` **in the same round**. Round 40 paid this.

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
- **A pin that asserts the current *wrong* answer is a signal, not a test to repair.** Its
  failure is the signal the widening landed. The pin this rule named,
  `test_the_letter_suffixed_chapter_gap_is_still_open`, was spent by round 18 and **no longer
  exists**; `tools/tests/test_structural_boundary_agrees_with_grammar.py` and
  `test_suffixed_chapter_cuts_the_section.py` carry the shape today.
- **`data/ocr_cache` stays 0 B** until OCR is deliberately taken in scope. Taking it in scope
  wakes the fidelity-floor invariants and routes sub-floor scans to `_provisional/`, which
  removes them from the portal.
- **`grammar.ROMAN_FOLIO_RE` is bounded at `ccxcix` and lowercase on purpose** — `mix` is
  both a valid roman numeral (1009) and an ordinary English word.

## And the one that governs all of it

**Fixed, or exempted with evidence traced to the source PDF. There is no third state.**
"Tracked and deferred" without an entry in `tools/suite/exemptions/<lane>.json` is a red
gate, not a decision.

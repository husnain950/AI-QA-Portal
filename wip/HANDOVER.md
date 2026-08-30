# Handover — where this stands, and how to pick it up

Review page: <https://claude.ai/code/artifact/775b061f-0cf0-46bd-bd5a-800a7cced45f>

Written 2026-08-30, after eight merged PRs (#46–#53). Everything below was measured, not
recalled; the commands that produce each number are in [Verification](#verification).

**One-line state:** the anomaly register is **64**, down from 210, it is now **gated on
CI**, and **16 of 48 checklist items remain open** — the hard residue of Phase 3, all of
Phase 4 and Phase 5, and the OCR work that was excluded by instruction.

---

## 1. What landed

| PR | register | what it actually was |
|---|---|---|
| #46 | 210 → 193 | a chapter numeral read three different ways by the body scan, the tree and the invariant |
| #47 | → 148 | the apparatus caption was never in a body — 45 hits inside a `title=` attribute, hiding a 473-footnote splice |
| #48 | → 92 | an unreadable glyph (`(cid:2)`), and two compilations exempted on evidence already accepted |
| #49 | → 78 | a split section code (`150 ZQR`), and a `ponytail:` measurement that had expired |
| #50 | → 75 | the contents page's own running title, parsed as a chapter |
| #51 | → 70 | a PART row parsed as a chapter; a chapter sort key that summed suffix letters |
| #52 | → **64** | a definition clause parenting a section to the wrong chapter; a marker run behind a space; a stale report hiding a broken generator |
| #53 | 64 | no parser change — the register is now committed and gated, and `make check` lints what CI lints |

**Three invariant classes are closed:** `body_chapters_in_tree`, `no_footnote_text_in_body`,
`structure_counts`.

Held constant across all eight: **80 / 11 / 12** documents, conservation **100.000%** on
body *and* footnotes, `data/ocr_cache` **0 B**, `signatures.json` moved exactly once
(PR #51) and deliberately, with **0 family changes**.

---

## 2. Where the register stands

`tools/suite/register.json` is the committed truth and CI compares against it.

| invariant | acts | rules | ordinance | total |
|---|---|---|---|---|
| `section_carries_its_body` | 15 | 17 | 5 | **37** |
| `no_foreign_section_start_in_body` | 10 | 9 | — | **19** |
| `section_codes_ordered` | 4 | — | — | **4** |
| `no_chapter_caption_in_section_heading` | 3 | — | — | **3** |
| `clause_codes_plausible` | 1 | — | — | **1** |
| **per lane** | **33** | **26** | **5** | **64** |

The rule has not changed: **fixed, or exempted with evidence traced to the source PDF.
There is no third state.**

---

## 3. The 16 open items

### Phase 3 residue — 5 items, 64 hits

This is genuinely harder than what has been closed. Rounds 1–7 each found *one cause
explaining many hits*. What is left is mostly **1–2 hits per document with different
causes**, so expect a lower hits-per-round rate from here.

**`section_carries_its_body` (37) and `no_foreign_section_start_in_body` (19)** move
together — the second invariant only fires when the victim leaf is itself heading-only, so
every one of its hits is the mirror of one of the first's. Fix start detection and both
move. Traced leads, none landed:

- **The five-stub block, Sales Tax Act 15.9.2021.** Sections 3B, 4, 5, 6, 7 are stubs at
  pages 40–43 while 7A, 8, 8A, 8B at pages 39–42 carry real bodies — the pages
  *interleave*. All five matched something at 40–43. **Read those source pages before
  theorising**; the shape suggests a contents-like block the stubs bound to while the real
  bodies bound elsewhere.
- **Customs 2008 s.181 and s.189** — heading-only, cause untraced.
- **`196K` `'to Omitted 96u'` and s.79 `'A O mitted'`** — omissions the invariant misses.
  Round 3 measured the intra-word-spacing tolerance at **one** hit and rejected it for
  precision; it is now two. Still marginal — revisit only if the count grows.
- **Run-together TOC lines**, Sales Tax 30.06.2021: `'33. Offences and penalties 33A.
  Proceedings against authority an…'`.
- **Ordinance (5)** lives in `fbr_ingest`, and two of them are a *footnote's text bound as
  a section body*. **Sequence these after Phase 4b** or the work gets done twice.

**`section_codes_ordered` (4)** — round 7 closed the 33A cause; these four are different
documents and untraced: Customs 2025 `'9' after '119'`, Sales Tax 2021 `'3' after '65'`,
Sales Tax 2014 `'3' after '32AA'` and `'22' after '75'`.

**`no_chapter_caption_in_section_heading` (3)** — all real leaks (`82A`, `32AA` ×2), each
an omitted-section placeholder whose heading ran on into the next chapter caption. Round 5
proved the invariant is right for these: the caps run matches a caption **on a chapter of
that document**.

**`clause_codes_plausible` (1)** — Finance Act 2024, jump `7 -> 8517`. **Do not weaken this
check.** Its own docstring says it is a detector for a cause that is not fixed (ledger
P06), and the hit is real: `8517` is an HS tariff heading inside clause 7's *quoted
amendment* (`1430 and 8517.1390)‖ shall be added. 8. Amendments o…`), and it swallowed the
real clause 8 — 54,667 characters. Two routes: bound the clause cursor by the measured gap
the invariant already uses, or reuse the quotation tracking `_common._QUOTE_CUE` already
has. Finance Act 2024 is `family=amending`, so `discover.py`'s P06 clause-title gate is
already on for it and is not catching this — start there.

**The 29 low-confidence documents** — now actually readable. §5 was printing **2** rows
until PR #52 fixed the generator, so this item was never really actionable before.

### Phase 4 — 3 items, none implemented

**4a — flip `--profile auto` to the default** and collapse the lane→package mapping to
family→profile. Phase 2 removed the reason not to: the family *overrides* the lane's
profile rather than replacing it.

**4b — the `fbr_ingest` decision is SETTLED and DEMONSTRATED, but nothing is wired.**
Measured from `signatures.json`:

| group | n | `container_order` | `chapter_lines` | `toc_rows` |
|---|---|---|---|---|
| Income Tax Ordinance 2001 | 21 | `PCD` / `CPD` | 13, 25, 499, 513 | 404 |
| **ICT (Tax on Services) Ordinance** | **9** | `''` flat | **0** | **3** |
| PSW Act / VDDA Act / PSW rules (acts+rules lanes) | 6 | `''` flat | 0 | 0–2 |

The 9 ICT editions are structurally identical to the flat instruments that already parse
fine in the *other* lanes, and nothing like the 13 Income Tax Ordinance editions they share
a lane with. Proven on the document, not inferred:

```
legal_ingest (acts binding)   assembled 3 / 3 sections; flat act -> synthetic root
                              s.1 235 chars, s.2 205, s.3 18,091 — real statutory text
fbr_ingest   (ordinance lane) RuntimeError: TOC parse left 3 section(s) without a
                              chapter container (1, 2, 3...)
```

**Both forks parse the same three sections.** The only difference is that `legal_ingest`
has a flat-act fallback giving them a container. So this is a **routing** problem, not a
parsing one. Decision: route by family, not by lane; `fbr_ingest` keeps only the 13 Income
Tax Ordinance editions; merging the fork stays the v1 non-goal it already is
(`README.md:283`). Follow-through unblocks 9 documents.

**4c — transport and deploy.** `make sync --metrics`, a mounted corpus volume in
`docker-compose.yml` and `northflank.template.json`, and an HTTP path writing
`version_metrics`. Docker is down on this host (recorded in Phase 1) and was never brought
up. The Northflank deploy is outward-facing and gated on green CI on `main` — **confirm
before triggering it.**

### Phase 5 — 4 items, not started

The instrument tree level: a level above chapter so a compilation parses as N instruments.
Its gate is the **deletion of the two Round 3 exemptions** that name it — Customs Rules
2001 (44 hits) and Federal Excise Rules 2005 (4). That deletion is the honest test that it
worked, and the suite will report them stale on its own once it does.

### OCR — 3 items, excluded by instruction

61 scanned documents / 2,456 pages; the 9 `--admit-below-floor` rebuilds; the ordinance
lane's other 10 text-layer documents (which now depend on 4b, not on OCR). There is a cheap
tail if it is ever wanted: **35 documents need ≤ 10 pages each, 172 pages total**, and
Finance Acts 2022 and 2023 are **one page each**.

---

## 4. How to work on this — the rules that were learned the hard way

**Never edit `packages/` while a conversion runs.** `convert_all.py` spawns a fresh child
per document, so each imports the parser *when it starts*; an edit mid-run gives early
documents the old code and later ones the new. A mixed-revision corpus looks completely
normal. This was done **twice** in one session, costing ~30 minutes. Kill and restart.

**Clear `__pycache__` after any mutate-and-restore verification.** Testing a lock by
patching a module, re-importing and restoring leaves stale bytecode: the source is right
while the module in memory is the version you rejected. Caught by `pytest`, after a
re-conversion had already run against it.

**Measure the invariant fix and the parser fix separately**, on identical JSON for the
first. Nearly every class is part wrong-invariant, part real defect, and a single total
hides both. `no_footnote_text_in_body` was 45 hits that were *all* a `title=` attribute,
concealing a 473-footnote defect.

**Measure candidate widenings against the corpus, as gained/lost — and know which corpus.**
A naive `MARKER_PREFIX` widening scored **1 fix : 17 false positives**; the narrowed form
scored **1 : 0**. But every measurement here uses `output/*.json` plain_text, and **that is
not what the parser sees** — the parser's line is `42 53 [202B.` while the rendering
collapses it to `42 53[202B.`. A lookahead anchored on `[` matched the JSON and missed the
PDF.

**Verify a lock by removing the fix.** A parenting lock passed with the fix stubbed out —
its two-chapter fixture let a later pass repair the damage. Three chapters reproduced the
real document.

**Read the comments before generalising.** `_DOTSUFFIX_RE` carried a measurement saying its
bracket gate was safe. Re-running it showed it had expired — but it was still right about
the danger, and dropping the gate outright gains 392 tariff rows.

**A cached artifact cannot tell you its generator is wrong.** Three instances this phase: a
`known_gaps` skip inside a check function (round 2), two `exemptions/` entries (round 3),
and `report.md` §5 — wrong from PR #45 to PR #51 because it had not been regenerated since
Phase 0. Only the `exemptions/` format reported itself stale, unprompted. That is the
argument for the register snapshot.

**Report fixes that moved the register by zero.** Round 4's acts lane and round 6's PART
fix were both correct and both scored nothing; folding them into a total would have
misattributed the rounds that did move it.

---

## 5. Verification

```sh
.venv/bin/python tools/run_suite.py acts        # and rules, ordinance
.venv/bin/pytest tools/tests -q                 # 56 passed, 1 skipped
.venv/bin/python tools/run_tests_smoke.py       # 13 package self-checks + lane suites
.venv/bin/python tools/discover_corpus.py --check
.venv/bin/ruff check                            # BARE — matches ci.yml
du -sh data/ocr_cache                           # must stay 0 B
```

Per round: snapshot `output/_pre_<round>/` before re-converting, re-measure all three
lanes, regenerate `tools/suite/register.json` **in the same PR**, and rewrite the register
in `wip/tasks.md` and `wip/plan.md`.

`run_tests_smoke.py` exits non-zero while the register is non-zero. That is expected and
pre-existing; it clears when Phase 3 reaches zero-or-exempted.

---

## 6. Two things to know about this session's output

**PR #51 shipped a broken `report.md`.** Its §5 lost 27 of 29 rows because the filter
tested `.profile`, which Phase 2 had turned into an override. Found and fixed in #52, but
it was live for one PR.

**An exported transcript is sitting untracked in the repo root**
(`2026-08-30-125158-*.txt`) and is **not gitignored** — a bare `git add -A` would commit
it. Delete it or add it to `.gitignore`.

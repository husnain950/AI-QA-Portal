# Vision-OCR sidecar: the four shortlisted scanned rules documents

**2026-09-24.** Ingests the four documents the shortlist left out because of their scanned
pages ([shortlist artifact](https://claude.ai/artifact/Y2MhMq2P3Mbgfzbp8xYWQp)). Before this
round, two had been refused at the OCR fidelity floor and two had never been converted.
Review page (image evidence, bake-off, per-document numbers): [Scanned Rules Ingested](https://claude.ai/artifact/SmQBw9pKum4gTzhdiMAmLy).

| document | pages | scanned (OCR'd) | before | after |
|---|---:|---:|---|---|
| Income Tax Rules 2002, upto 24.11.2023 | 946 | 27 (15; 1–12 are TOC) | refused, **62.7%** agreement | ingested, 99.94%, **7 tokens flagged** · structure defects, see below |
| PSW Deputation/Secondment Regs 2021 | 20 | 20 | refused, **74.3%** | ingested, 100%, **65/65 invariants** |
| Sales Tax Rules 2006, upto 31.08.2021 | 241 | 5 | never converted | ingested, 100%, **63/63** (2 traced exemptions) |
| Sales Tax Rules 2006, upto 31.10.2023 | 251 | 6 | never converted | ingested, 100%, **63/63** (2 traced exemptions) |

## How it works — the conversion path still calls no model

`README.md` excludes LLM/vision from the conversion path, and it still is excluded:

1. `tools/vision_ocr.py transcribe <pdf>` sends each scanned page to **three vision models**
   **offline** via OpenPaths. It caches each raw reply as `<pdf>.vision/p<N>.<model>.txt`,
   and refuses a truncated (`finish_reason != stop`) or empty reply.
2. `tools/vision_ocr.py vote <pdf>` votes the readings token by token.
   - The **medoid** reading is the anchor. A model that gave up on a page is never the
     spine.
   - An order-free per-token median rescues text that two readings carry in a different
     reading order, such as form sidebars.
   - Layout (`|`, `☐`, `____`) and the prompt's own `[handwritten]`/`[stamp]` notes are
     stripped.
   - Output is `<pdf>.vision.json`.
3. Splits are **ruled on against the page image** in `<pdf>.vision.rulings.json`. That file
   survives a re-vote, and each ruling pins the token it expects, so a changed vote fails
   loudly instead of silently mis-applying the ruling.
4. `legal_ingest.ocr.ocr_page` reads the sidecar **deterministically**.
   - Text and line order come from the vote. Line geometry comes from the best-matching
     Tesseract line: the longest in-order run of matches is kept, the rest are
     interpolated, and lines stay ≥4pt apart so `LINE_TOL` never merges them.
   - A PDF without a sidecar keeps its old cache key and its old output.
   - `metadata.ocr.engines` records `vision:<models>`.

Sidecars and rulings sit next to their PDFs under `data/corpora/rules/Rules/` (gitignored,
like the PDFs). They are the frozen input and must be kept with the PDF.

## Choosing the panel

A bake-off ran 8 models on 6 pages. The table scores each model on **15 tokens I verified
against 300–400 dpi crops**. The traps: source typos printed as-is (`docuemnts`, `Invidual`),
codes (`64010056`, `64050052`), refs (`152(1AA)` vs `152(1AAA)`, `u/c (5A)`), and a signatory
name.

| model | missed / 15 | failure mode |
|---|---:|---|
| **claude-sonnet-5** | **0** | — |
| **claude-opus-5-5** | 1 | honest `[?]` on illegible codes |
| **gemini-2.5-pro** | 2 | on unreadable text it **invents** plausible wording (`Betting`, `165A`) |
| xiaomi/mimo-v2.6-pro | 2 | silently fixes typos |
| grok-4.7 | 3 | digit slips (`64010055`, `@6%`) |
| qwen3.8-flash | 5 | normalises `u/c`→`u/s`, `NSC`→`NDC` |
| gpt-5.6 | 10 | rewrites content (`drivers salary`→`employee share`, `154(3)`→`154(2)`) |
| gpt-5.5 | 11 | same |
| gemini-3.8-flash | — | leaked its chain of thought into the transcription; dropped |

The panel is Sonnet 5 + Opus 5.5 + Gemini 2.5 Pro, with Gemini as the third vendor. Two
models agreeing can still be wrong on a digit, so every legally load-bearing split was
checked by eye.

## Adjudication

| | ITR | PSW | STR 2021 | STR 2023 |
|---|---:|---:|---:|---:|
| OCR'd pages | 15 | 20 | 5 | 6 |
| voted tokens | 8,758 | 5,641 | 1,765 | 2,656 |
| rulings against the image | 105 | 42 | 15 | 19 |
| still flagged `needs_review` | **7** | 0 | 0 | 0 |

- The OpenPaths key **ran out of credits** after ~190 calls. On the 12 pages left with two
  readers, I ruled on every disagreement from the image, which is the same result as a third
  vote where the two models disagree. ITR p940/941 had only Sonnet's reading, so they were
  **proofread in full**.
- **ITR p684** is a low-resolution IRIS screenshot. Sonnet gave up on it, Opus wrote `[?]`
  for every code, and Gemini invented codes. My own transcription from zoomed crops stood
  in for Sonnet. Its codes are corroborated against the same codes typeset cleanly on p482
  and p641.
- Readings the models got wrong and the rulings fixed:
  - ITR p491: every 236-series code (`6415…`→**`6416…`**, row 19 `64080201`).
  - ITR p525: `9089`→**`9009`**.
  - PSW p6: signatory `FARIQ`→**`TARIQ`**. The glyph is a broken T, and the letter on p7
    spells the name `Tariq`.
  - PSW: handwritten file folios (`-306-`, `89`, `297`) and signature dates deleted.
- **The 7 flagged tokens are ITR only.** Three p491 code endings (rows 37, 38 and 54: 5 vs 6,
  6 vs 8, 8 vs 9) and three p684 codes are illegible in the source and have no clean copy
  elsewhere. p684's `64220259` is kept as a best reading, still flagged. They carry
  `needs_review` into the portal.

## One parser fix, measured

Sales Tax Rules rule **150X** prints its doubled terminator across the wrap, as
`…invoices.-` / `- (1) The registered buyer`. The existing doubled-terminator rule only
handled one line, so the body opened on a stray dash and hid `(1)` from `_classify`.

- `_find_heading_split` now gives the dash-only tokens of the next line to the heading.
- The two heading strippers (`builder._body_heading_title`, `discover._heading_from_words`)
  strip a spaced dash run.
- **Reach, censused over all 60 acts+rules PDFs: 4 lines, all rule 150X,** in Sales Tax
  Rules 30.06.2020 and 31.12.2020 (both off-corpus), plus the two new editions.
- Re-converting all four documents changed **exactly one leaf each** in the two new
  editions (150X html), and PSW and ITR came out byte-identical.
- Tests: `tools/tests/test_doubled_heading_terminator.py`, which fails with the fix disabled.

## Exemptions — traced, enumerated

Both new Sales Tax editions carry the corpus edition's source defects. Each is written as
its own entry in `tools/suite/exemptions/rules.json`:

- **`no_jammed_words`**: each hit is **one pdfplumber word of 65–91 characters with zero
  space glyphs and no gap above 0.28pt**. There is nothing positional to split on, which is
  the same cause as the 01-01-2025 edition's entry.
- **`section_carries_its_body`** covers 3 enumerated leaves:
  - 44A prints `“44A.-`, the quote error the 01-01-2025 entry already traces.
  - 150ZEI and 150ZEJ exist only in the **stale contents** (p11). The body prints CHAPTER
    XIV-AB as `[**omitted**]` and runs straight from 150ZEG to 150ZEK.

## Verification

- `legal_ingest.ocr._demo` has new sidecar fixtures. **5 of 5 mutants are killed**: dropping
  the in-order guard, the 4pt line step, the 0.5 match floor, the settled-vote rule, or the
  sidecar hash in the cache key each fails a fixture.
  - Mutants must run with `python -B`: an equal-length mutant restored within the same
    second leaves a `.pyc` that still looks fresh.
- `tools/run_tests_smoke.py`: byte-identical to `main` apart from paths, which already fails
  4 steps with or without this change.
- `pytest tools/tests` + provenance: 3 failures, the same 3 as `main`.
- **Rules lane:** PSW and both Sales Tax editions pass. ITR fails (below). Federal Excise
  2005, Inland Revenue 2021 and S.R.O.406 already fail on `main`.
- **Portal, end to end:** migrated a throwaway DB, synced the four documents, and ran the
  worktree API and web on side ports.
  - The review pages serve the voted text (`docuemnts` verbatim, `TARIQ`, the `6416…`
    codes), and all four PDFs return 200 via `/uploads`.
  - `visual_smoke.mjs` on a scanned page of each passes **4/4**.
  - The DB was dropped afterwards. The shared compose stack was never touched.
- `data/ocr_cache` is still **0 B** (the cache is `packages/.ocrcache`).

## Open — not done in this round

- **ITR 2002 structure**, shipped as-is on request. The parser cannot structure this
  edition: rule 232 spans pages 150–625, only 87 of 182 rules are assembled, and 12
  invariants fail (`section_carries_its_body` 94, `section_codes_ordered` 50,
  `structure_counts` 55). This is independent of OCR: only one failing leaf touches a
  scanned page. No ITR edition had been ingested before.
- **PSW regulation 5 absorbs pp.6–20.** The file is a covering letter, the gazette, and two
  annexes that reprint the same five regulations, and the annexes land inside regulation 5.
  This is structure, not OCR.
- `tools/suite/register.json` is committed empty and was already stale on `main`. It was not
  regenerated, because that would bake ITR's defects in as the accepted baseline.
- Removed as unused: whole-page strip tiling for dense screenshots. If a future run needs
  it, the approach is to cut on the whitest row near each boundary.
- **Rotate the OpenPaths key** used for this run. It was pasted into a chat session.

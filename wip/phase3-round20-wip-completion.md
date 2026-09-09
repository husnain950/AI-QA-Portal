# Phase 3–5, round 20 — complete the current ledger (PR #86)

Closes the owner-approved program through Phase 5 on
`cursor/complete-current-wip-1c52`. OCR stays out. The private 190-document
corpus was **not** on this host; live checks used official public FBR PDFs
plus corpus-free fixtures. **`tools/suite/register.json` stays at 22** — it
was not regenerated from a partial public corpus.

## What this PR actually did

Work landed across several commits on this branch. This file is the round
artifact; it does not rewrite earlier `wip/phase3-round1*.md` files.

| ledger row | what shipped | live evidence on this host |
|---|---|---|
| heading-terminator / 32AA cluster | omission-aware `_find_heading_split` fallback; stops at structural boundary / next code / TABLE caption | fixture green (`tools/tests/test_omitted_heading_stops_at_boundary.py`). Three private Sales Tax editions not reconverted. |
| omission spellings | `_is_omission` accepts whole-string `"to Omitted 96u"` and `"A O mitted"` only | no broad `\s*` regex. Private Customs 2024/2025 not present. |
| `preamble_carries_no_toc_tail` | extra TOC-tail signal besides `rows>=3`; `SHCEUDLE` still refused | public Customs 30.06.2008 and Sales Tax 30.06.2023: **0** hits. Register's 2 remain the private editions. |
| `clause_codes_plausible` | `_DOTFORM_RE` uses `\.(?!\d)` so `8517.1430` is not a clause | public Finance Act 2024 reconverted: clauses **1–12**, invariant **0**. Check not weakened. |
| CHAPTER en-dash | grammar / builder / discover / `_STRUCT_LINE` agree on `CHAPTER – VI` | known-gap test moved to `BOUNDARIES`. Private 21-document set not re-converted here. |
| schedule PART reader | Arabic `Part-1`/`Part-11` accepted; gazette glyph-split `P ART -I` classified | see below. |
| family routing (P4-2) | route by family, not by lane; forks **not** merged | 9 public ICT PDFs → `legal_ingest` + synthetic root, 3 sections each. |
| `--profile auto` default (P4-1) | convert CLIs default to `auto` | flipped **without** a full-corpus reparse. Register still 22, so a mixed-revision full reparse was not run. |
| cross-edition gate (P3-8) | `tools/check_cross_edition_quality.py` on tree counts | skips without corpus; unit tests lock the 50% collapse rule. |
| instrument tree (Phase 5) | `instruments[]`, `type=instrument`, `inst:` keys; Alembic `0006`; portal breadcrumbs | compilation exemptions for Customs Rules 2001 and Federal Excise Rules 2005 **deleted**. Remaining rules exemptions are jammed-tokens, split-ordinals, and the round-19 STR printing errors. |

## The schedule PART reader — diagnosed, then fixed

Round 17 located 20 hyphenated PART lines in Finance Act *schedule* bodies and
left the cause unknown: `_kind()` already returned `"part"` for 18 of 20, so
the pattern was not the whole story.

Two parser defects were real:

1. **Arabic numerals.** `_PART_RE` was `[IVXL]+` only. `Part-1` / `Part-11`
   failed. Widened in an earlier commit on this branch; locked by
   `tools/tests/test_schedule_hyphenated_parts.py`. Do **not** collapse `l`→`I`
   (`Part-Il` stays `PART IL`).
2. **Gazette glyph-split**, found on the public PDFs. `extract_text` prints
   `PART-I`; the page model, which splits on font-subset changes, emits
   `P ART -I` / `P ART - IV`. `_kind` required a contiguous `PART` keyword, so
   those lines stayed in TABLE/PART bodies. `grammar.spaced('PART')` already
   tolerated this on contents rows; the schedule reader did not.

Public Finance Act 2021 (230 pp) and 2019 (258 pp), reconverted after the
glyph-split fix:

| document | Fifth Schedule parts after |
|---|---|
| Finance Act, 2021 | `PART I`–`PART VIII` plus the existing `TABLE-I/II/III` nodes. No leftover whole-line PART in bodies. |
| Finance Act, 2019 | `PART I`–`PART VII` (was I, V, VI only). |

Parenthetical sub-parts (`PART-V(A)`, `PART V(B)`) stay content — they are not
PART nodes. The 8.5pt heading-size gate is unchanged. Public Finance Act 2025
prints no schedule PART headings; public Finance Act 2014 has no text layer
(OCR out of scope).

The 8.5pt gate remains the explanation for any private-corpus line that is a
lexical PART and still sits in a body: do not lower it.

## Compilation detection (Phase 5 follow-through)

Public **Federal Excise Rules 2005 (30.06.2015)**: two instruments
(`S.R.O. 534(1)/2005` + `ELECTRONIC FILING… RULES, 2005`). Compilation
exemptions deleted. Suite 60/60 on that file plus `fe_r78_double_hyphen_heading_keeps_body`.
Still exempt: `no_split_ordinals` (pre-existing, traced).

Public **Customs Rules 2001**: body discovery 1102 sections / 41 chapters.
Compilation exemptions deleted. `customs_2001_is_a_compilation` is active and
PASS. Still exempt: `no_jammed_words` (75-character jammed token; not Phase 5).

Along the way, untitled one-sentence rules, digit `5561`→`556I`, untitled
rules before tables, regular-font table-introducing rules, and unmodeled
`SUB CHAPTER (N)` captions were repaired so they do not become orphan list
items.

## What this host could not close

The committed register is still **22**. These rows need the private corpus
or OCR, neither of which is in scope here:

- 32AA cluster on three Sales Tax Act editions
- Customs 2024 `to Omitted 96u` / 2025 `A O mitted` (invariant widened; pages
  not present)
- register's two `preamble_carries_no_toc_tail` hits (private editions)
- PSW ministry list, PFMA s.26 (public PDFs had no text layer)
- Sales Tax 2014 `(cid:2)` 
- Sales Tax Rules `no_foreign_section_start_in_body`
- ordinance five on **Income Tax Ordinance** editions (`fbr_ingest`). Public
  ICT PDFs are a different family and were only a routing proof.
- FA2025 / FA2014 schedule PART lines from the private scan set

`--profile auto` is the convert default. Do not run `make convert-all`. Do
not write `register.json` from the public subset staged on this VM.

`data/ocr_cache` holds only `.gitkeep` (0 bytes of cache).

## Local pytest vs CI

`tools/tests` on this VM with a **partial** public corpus will fail
`test_register_snapshot.py` (measured counts are not the 103-document
register) and `test_shipped_exemptions_match_exactly_one_corpus_document`
(Sales Tax Rules 2006 30-06-2025 is not staged). Both **skip on CI**, where
there is no corpus. Those failures are not a signal to delete exemptions or
rewrite the snapshot.

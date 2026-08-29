# Phase 3, class 3 — two compilations, and a glyph nobody can read

Review page: <https://claude.ai/code/artifact/17d59d3c-75fd-48e6-a664-e2ac6c53b550>

Follows [`wip/phase3-legal-reference.md`](./phase3-legal-reference.md) (PR #47). Takes the
largest class, `section_carries_its_body`, from **111 to 55** without touching the parser
— the JSON is byte-identical to what round 2 produced. Everything here is either the
invariant being wrong or a document the pipeline genuinely cannot express.

| | before | after |
|---|---|---|
| register | 148 | **92** |
| `section_carries_its_body` | 111 | **55** |
| exemptions on the rules lane | 8 | 8 |
| documents (acts / rules / ord.) | 80 / 11 / 12 | unchanged |
| re-conversion | — | **none needed** |

## 1. `(cid:2)` is not a character, and it is not recoverable

`_is_omission` decides whether a heading-only leaf is *legitimately* empty — the law
omitted that section, so there is no body to carry and the invariant must not fire. It
matches `omitted|repealed|***` against the heading and the body.

Eight leaves print their omission as `Omitte(cid:2)d`.

`(cid:N)` is what pdfplumber emits for a glyph whose font subset carries no ToUnicode
entry. The obvious question is whether it can be recovered, and the answer — measured on
*The Sales Tax Act, 1990 (01.07.2014)*, which holds 250 of the corpus's 279 occurrences —
is **no**:

- The producer emitted dozens of separate `LinuxLibertineG` subsets, each with its own
  small CMap.
- Glyph `<02>` maps to a **different character in each one**: `r` in `HAAAAA+`, `8` in
  `JAAAAA+`, `4` in `ABAAAA+`, `l` in `DBAAAA+`.
- The subsets that actually print `(cid:2)` are precisely those whose CMap has **no `<02>`
  entry at all** — including `BAAAAA+`, which has 83 entries and skips that one.

So there is no consistent mapping to recover, and none is written down. The character is
unreadable, and it lands mid-word: `hav(cid:2) b(cid:2)(cid:2)n (cid:2)xport(cid:2)d`.

Dropping it before the keyword match is what lets `Omitte(cid:2)d` be read as the omission
it is. **111 → 103.**

### Two widenings measured and rejected

Both were in the plan; both turned out to buy nothing worth their cost.

| candidate | hits | verdict |
|---|---|---|
| strip `(cid:N)` | 111 → **103** | kept |
| also accept a dot-run (`2[15. ... ]`) as an omission marker | 103 → 103 | **rejected — zero.** Those six leaves carry `Omitte(cid:2)d` as their *heading*, so the cid strip already catches them; the ellipsis is a second signal for a case already covered |
| also tolerate intra-word spacing (`A O mitted`) | 103 → **102** | **rejected.** One hit, for `o\s?m\s?i\s?t\s?t\s?e\s?d` in a regex whose job is precision |

## 2. Two compilations, exempted on evidence already accepted

48 of the remaining hits are two documents that are not one instrument each.

**Customs Rules, 2001 — 44 hits.** 563 pages binding 44 separately-notified S.R.O. rule
sets behind one index. The tree has no level above chapter, so the index rows *become* the
section leaves, and an index row has no body to carry:

```
Passenger's Baggage (Import)Rules. 570(I)/98 dt.12.06.1998
Frustrated Cargo Export Rules 3(I)/70, dt 2.1.1970 86-89
```

**Federal Excise Rules 2005 — 4 hits.** PDF page 75 starts a second instrument inside the
body — *Electronic Filing of Federal Excise Return Rules, 2005*, with its own CONTENTS
page — whose rows are parsed as this document's rules 1–4, carrying leader dots where
their text should be.

Neither is new evidence. Both documents already carried exemptions on sibling invariants
for exactly this cause, and Customs Rules 2001 also carries a `known_gap` case
(`customs_2001_is_a_compilation`). The invariant is right; the pipeline cannot express the
document. The fix is the instrument tree level, now written down as **Phase 5**, and the
test that it worked is the deletion of these two entries.

## 3. Two exemptions the suite told us to delete

Adding entries made the runner re-check the existing ones, and it reported two as **no
longer failing**:

- `Customs Rules, 2001` / `no_orphan_marker_li`
- `Federal Excise Rules 2005` / `section_codes_ordered`

Both were fixed by earlier rounds and nobody noticed. Deleted, as the report instructs.

This is the same lesson round 2 learned from the opposite direction. There, a skip
hardcoded *inside a check function* had gone stale silently, because nothing re-examines a
condition buried in code. Here, the declared format did its job unprompted: **the suite
found the dead entries as a side effect of an unrelated change.** The rules lane ends this
round with 8 exemptions — two added, two removed.

## Gates

| gate | result |
|---|---|
| `ruff check` (bare, as CI runs it) | clean |
| `pytest tools/tests` | 53 passed, 1 skipped |
| stale exemptions, all three lanes | **0** |
| parser changed | **no** — `packages/` untouched |
| re-conversion | not needed; JSON byte-identical to round 2 |
| documents | 80 / 11 / 12, held |
| `data/ocr_cache` | 0 B |

## What is left in `section_carries_its_body` (55)

Triaged from measurement, not assumption:

- **14 — a split code.** The text layer prints `150 ZQR.` for `150ZQR`, and
  `_candidate_code` requires the code contiguous, so it returns `None` for an entire
  18-section run (Sales Tax Rules 2006, pages 143–152).
- **~24 — real zoning misses**, scattered 1–2 per edition.
- **3 — a TOC row bound as body**, e.g. `33. Offences and penalties 33A. Proceedings…`.
- **5 — ordinance**, which is `fbr_ingest`. Two of them are a footnote's text bound as a
  section body. Sequenced after the Phase 4 decision on that fork, so the work is not done
  twice.

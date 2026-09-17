# Round 38 — QA Cycle 1, Federal Excise Act, 2005

A QA cycle logged **19 rows** against the review portal's rendering of
`Federal Excise Act, 2005 as amended upto 30-06-2025`
(`/review/cb324fb0-da93-472b-ba33-44c9ac00000b/...`). Every row was re-checked
against the source PDF's own glyph geometry — not against the portal, and not
against the reviewer's prose.

**18 are real, 1 is not.** They are not 18 bugs: they collapse to **9 root
causes**, and each cause fires on far more than the one document the reviewer
opened. This PR closes **16 rows with 7 fixes**; the two tariff-table rows are
held for PR 2.

The prod API is auth-gated, so the document UUID could not be read directly.
The edition was identified by an eleven-page-number fingerprint — s.27→41,
s.29→43, s.30→48, s.31→49, s.34→52, s.38→55, s.43A→60, s.46→63, s.47→66,
s.47AB→68, FIRST SCHEDULE→72 — which matches exactly one of the 17 staged
Excise editions.

---

## The reviewer found one instance each of corpus-wide classes

Measured across the staged corpus **before** any code was written:

| Class | reviewer's row | sites corpus-wide, before |
|---|---|---|
| orphaned heading terminator | CH5-04, CH6-03 | **412** leaves / 30 documents |
| schedule title missing from the leaf | FS-01 | **237** leaves / 34 documents |
| ordinary numerals read as citations | FS-03/04/05/08 | **80** in a 10-document sample |
| gazette title on body prose | CH6-01, CH6-05 | **~24** blocks |
| citation glued to a table caption | FS-03 | **20** / 11 documents |

That is why each is fixed at its root and pinned with an invariant, rather
than patched at the leaf the reviewer opened.

---

## CH4-01 is not a defect

The row says Section 27's marker `41.1` wrongly opens Section 26's note, and
asks for the marker to be left unresolved.

PDF page 41 prints a **genuine superscript `1`** at `x0=197.6, size=8.04,
TimesNewRomanPSMT` immediately before `[or beverages]`, and page 41's footnote
1 is literally *"Sub-section (1) substituted by Finance Act, 2020."* Footnote
numbering in these compilations restarts **per page, not per section**, and
this compilation reuses `1` on that page. The same shape is in the 2023 and
2024 editions. The portal is reproducing the printed page correctly.

Doing what the row asks would unresolve every legitimately reused marker in
the corpus — `43.2` twice in s.29, `83.2` twice in Table-II — so it costs real
citations and buys nothing the source supports. Closed **Won't Fix**, with
`tools/tests/test_page_scoped_footnote_reuse_is_faithful.py` pinning the
behaviour so a later round does not "fix" it.

---

## The seven fixes

| # | Cause | Rows | Where |
|---|---|---|---|
| A | `_classify`'s marker strip requires a `[`, so a marker kerned onto the list marker is invisible | CH5-01, CH6-02, CH6-04 | `builder.py::_classify` |
| B | `footnotes._join` had no gap glue, unlike the body renderer | CH5-02 | `footnotes.py::_join` |
| C | `BRACKETS_ONLY_RE` rejected `*`, so `[31***]` was never claimable | CH5-03 | `footnotes.py` |
| D | heading split took the first dash of a doubled terminator | CH5-04, CH6-03 | `builder.py::_words_after_heading_dash` |
| E | the list loop absorbed every `text` row with no geometry | CH5-05 | `builder.py::_render_line_run` |
| F | `_gazette_block_class` fired on body prose | CH6-01, CH6-05 | `builder.py::_gazette_block_class` |
| G | a schedule's title never reached its leaf | FS-01 | `schedules.py::_finish_leaf` |
| H | the marker size gate was per-document, not per-line | FS-03/04/05/08 | `pagemodel.py::_tighten_markers_on_small_lines` |
| J | each page was its own footnote run | FS-06 | `pipeline.py::_next_page_notes` |

Three of these were **redesigned by measurement**, and the discarded versions
are worth recording:

- **F** — the obvious fix is to drop `re.I` or gate on the preamble. Both are
  wrong. `_GAZETTE_TABLE_CAPTION_RE` also returns `act-title`, and **109 of
  the 253 non-preamble gazette blocks are legitimate in-section `TABLE`
  captions**; a further **11 uppercase `AN`/`ACT` blocks sit inside numbered
  sections legitimately**, because a Finance Act host clause reprints a whole
  Act. What actually separates a false positive is that it *continues a
  sentence*.
- **H** — the first formulation (line-modal size alone) **lost 22 real
  markers**; adding the bracket-adjacency exemption fixed that, and a second
  pass showed it still lost p.82's marker `1`, which sits alone on its own
  line group because its superscript baseline is 3.5pt clear of the text and
  `LINE_TOL` is 3.0. Both conditions exist because the measurement demanded
  them, not on principle.
- **E** — the plan called for threading geometry through `_layout_blocks` and
  `_build_html` as a 4-tuple. Carrying a row *kind* (`ptext`) instead touches
  two lines and no call sites.

---

## Verification

- `pytest tools/tests` — **297 passed, 1 skipped** (baseline 245 + 52 new).
- 14 package self-checks pass.
- `ruff check` bare — clean.
- All 16 rows re-checked by reading the re-converted leaf html, not by
  trusting a test.

### The reviewer's document, before → after

Unresolved `<sup class="marker">` sites: **14 → 6**.

Closed: `76.17`, `76.18`, `76.22` (fix H — they were never markers),
`79.4/6/7/8` and `100.1` (fix J).

Left, and why:

- `42.3` ×2 and `61.5` — fix J **correctly declines** these. Page 43 has a
  note 3 but page 43's own body also cites 3; page 62 has a note 5 but page
  62's body also cites 5. Contested, so not borrowable. The plan predicted
  these would close; the guard is stricter than estimated, which is the safe
  direction.
- `76.19` / `76.20` — p.76 prints `19&20` as one 9.0pt token whose only line
  neighbours are 11.0pt brackets, so the line-modal test cannot reach it.
  Already the case before this round. Recorded in the tracker.
- `89.3` — out of scope, unchanged.

Marker census on the same document, main vs this tree: **515 → 412, 103 lost
and 0 gained, every one of the 103 a false positive.** Ninety-four are on the
contents pages, where section numbers *and* page numbers were both read as
citations (`1 Short title, extent and commencement. 5` yielded markers `1` and
`5`); `toc.py` never consults `is_marker`, so those were inert. The other nine
are the four QA rows.


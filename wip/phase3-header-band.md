# Phase 3, round 10 — a band with no evidence behind it

Review page: <https://claude.ai/code/artifact/6aa23bc8-f4a6-4968-8550-0deda7343cb4>

Follows [`wip/phase3-cursor-cascade.md`](./phase3-cursor-cascade.md) (PR #56).

**44 → 33**, the largest single-round drop since round 3. Four documents changed and every
change is a **gain**: net +3,904 characters, nothing lost anywhere in the corpus.

## The cluster, and what it was not

Sales Tax Rules 2006 (01-01-2025) held **16 of the 64 hits** the register opened this
session with — a quarter of it in one document, against 2 in its own sibling edition. Round
9's fix to `why_unbuilt.py` made the lane diagnosable for the first time, and the answer was
nothing like round 9's:

```
code       exp found pages   branch   cursor  note
2           20 [116, 169, …] NONE          9  nearest available occurrence is 96 page(s) away
35          59 []            NONE       1138  code never opens a body line
39E         62 []            NONE       1330  code never opens a body line
44A         66 []            NONE       1452  code never opens a body line
76          88 []            NONE       2061  code never opens a body line
101         93 []            NONE       2215  code never opens a body line
150W       109 []            NONE       2714  code never opens a body line
150X       110 []            NONE       2714  code never opens a body line
150ZQT     144 []            NONE       3759  code never opens a body line
150ZQW     145 []            NONE       3806  code never opens a body line
150ZQZI    151 []            NONE       4007  code never opens a body line
150ZQZL    152 []            NONE       4051  code never opens a body line
```

No cursor poisoning. **Eleven of the twelve are "code never opens a body line"** — the
grammar never saw them at all. And `pdftotext` says the bodies are certainly there:

```
2547:   35. Responsibility of the claimant.—The automated processing of refund claims shall be
3804:   76. Power to require information to be furnished.--The referring authority or the
4028:  101. Attachment of property in partnership.-- (l) Where the property be attached consists
4771:  150X. Same conditions to apply in respect of buyer for receiving electronic invoices.--
```

They print on exactly the pages the contents page predicts. They are not in `body_blocks`.

## The cause: a header band measured from a header that does not exist

```
p 59  '35. Responsibility of the claimant.—…'   top = 41.1
p 88  '76. Power to require information…'        top = 41.0     header_max_top = 43.6
p 93  '101. Attachment of property…'             top = 41.1
p110  '150X. Same conditions to apply…'          top = 41.5
```

`calibrate` finds no running header in this document — `running_header=''`,
`header_keys=[]` — so `header_max_top` falls back to

```python
        running_header, header_max_top = "", page_h * 0.055
```

a flat 5.5% of the page, which is not a measurement of anything. `_is_header_line` then
dropped every line above it.

That function exists for precisely this. Its docstring is ledger **P37**, where Federal
Excise 01.07.2017's whole THIRD SCHEDULE title block was discarded and its content appended
to the SECOND SCHEDULE, and it states the principle plainly: *"deciding what a line is from
where it sits instead of from what it says."* But its guard only applied where a header had
been **detected**:

```python
    keys = getattr(cal, "header_keys", ()) or ()
    if not keys:
        return True                       # no header detected: positional band
```

with the reasoning that there is nothing to match against and the 5.5% band is
conservative. It is conservative about keeping headers **out**, and the exact opposite
about keeping law **in**. This document prints no header, so the top of a page is simply
where the next rule begins — and four rules begin there.

## The fix, and why it is not just "keep everything"

`_is_header_line` gets **shorter**:

```python
    if ln.top >= cal.header_max_top:
        return False
    txt = ln.text().strip()
    if not txt or not any(c.isalpha() for c in txt):
        return True                       # blank, or a bare folio
    return _FOLIO_RE.sub("#", txt) in (getattr(cal, "header_keys", ()) or ())
```

For a document with a detected header this is byte-for-byte the same decision. The change
is that "no keys" now means "keep the text", and `calibrate` fills `header_keys` from
**recurrence** when nothing clears its 40% threshold:

```python
        keys = {k for k, cnt in header_texts.items()
                if cnt >= 2 and sum(c.isalpha() for c in k) >= 8}
```

That rule was measured before it was kept. Of the corpus's **50** documents that reach this
branch, **five** do have a header the 40% test missed:

| document | what recurs |
|---|---|
| Public Finance Management Act 2019 | `'#(cid:#) THE GAZETTE OF PAKISTAN, EXTRA., JU…'` and `'PART I](cid:#) THE GAZETTE…'` — a gazette alternating recto and verso, so each variant sits near half and neither clears 40% |
| Finance Act 2023 | `'NATIONAL ASSEMBLY SECRETARIAT'` |
| Income Tax Rules 2002 | a per-CHAPTER header, six variants |
| Sales Tax Act 15.9.2021 | repeated table column headers |
| Customs Act 11.03.2019 (Urdu) | its Urdu masthead |

The other 45 have none — Sales Tax Rules 01-01-2025 among them, where every top line is
unique. So the band still drops what repeats and now keeps what does not.

## A wrong turn worth recording

I measured Income Tax Rules 2002 as leaking **189** header lines under the new rule, and
started building a full-document band census to stop it — cropping each page to the 44pt
strip, ~15s on a 318-page document. Then I ran the **old** code on the same document and got
the identical 189.

That document has a *detected* header (`CHAPTER - XIX MISCELLANEOUS` clears 40%), so it
never reaches the fallback branch at all. The leak is pre-existing, untouched by this
change, and the census was 17s per document buying nothing. Reverted.

The lesson is the one already in the handover, in a new costume: **measure the before, not
just the after.** A number that looks like a regression is not one until the old code has
been asked the same question.

## Measured: 4 documents changed, every change a gain

| lane | document | leaves | bound | characters |
|---|---|---|---|---|
| rules | Sales Tax Rules 2006 (01-01-2025) | 339 → 339 | 338 → 339 | 445,377 → **448,927** |
| rules | AML_CFT Sanction Rules, 2020 | 8 → 8 | 8 → 8 | 8,931 → **9,263** |
| acts | The Tax Laws (Amendment) Act, 2020 | 5 → 5 | 5 → 5 | 40,423 → **40,442** |
| acts | The Pakistan Single Window Act, 2021 | 23 → 23 | 21 → 21 | 30,227 → **30,230** |

Net **+3,904 characters, 0 lost**. Leaf counts held everywhere. The conservation audit
cannot see text that is *added*, so the additions were read instead:

```
AML_CFT s.2  + 'c) “AML/CFT Regulations” means any regulations, directives,'
        s.4  + 'vii) the extent to which the contravention was negligent or willful; or'
        s.6  + '2) Where a monetary penalty has been imposed and if the person'
Tax Laws (Amendment) 2020 s.2 + 't'   s.3 + 'y'   s.4 + 'on'
```

Every one is statute. The single characters in the Tax Laws Act are the calibration comment
coming true from the other side — that edition prints bare folios at the top of successive
pages, and the band had been shaving the first glyphs off its real first line.

## The three that remain in that document, each traced

- **44A** — the body prints `“44A. -Selection and conduct of audit.-(1) …`. A left double
  quotation mark opens the line, so `_candidate_code` never reaches the code.
- **150ZQZI** — the contents page says `150ZQZI` (capital i); the body prints
  `150ZQZl. Functions of the licensing committee.—` (lowercase L). The folding does not
  unify them.
- **150W** — its code appears only inside a footnote,
  `'228 The rule 150W is substituted by SRO 1525(I)/2023 dated 10-11-2023'`.

And one more from the same document that is not a band problem at all: the contents page
lists rule **39E**, the body prints **`39K. Risk management in refund processing`** — same
title, different code. A renumbering the contents page did not follow.

## The failing regression case, traced to the source

`str_bracketed_chapters_classify` was red on `ELECTRONIC OROTHER MEANS`. The parser is not
at fault — the caption is set over three lines and pdfplumber returns the third as a single
token:

```
'OR'       x0=255.9  x1=276.9   (line above)
'OROTHER'  x0=238.8  x1=310.6   <- one word, no space in the text layer
```

That is this document's documented `no_jammed_words` cause, which it already carries an
exemption for (`'whetherthemonthlyreturnsfurnishedbytheregisteredpersoncorrectlyreflect'`
arrives as one token). The case was asserting a de-jammed string the parser could never
produce, so it was failing on a defect it does not test. Its `arg` now matches the source
and its description carries the measurement; it still fails if bracketed-chapter
classification regresses. That document is **cases 2/2**.

## A process gap, named rather than fixed

Two background re-conversions were killed mid-run, leaving 49 of 80 acts documents at the
new revision and 31 at the old — the mixed-revision corpus the handover's first working rule
is about. `convert_all.py --skip-existing` does not help: it skips by *existence*, and after
a re-conversion every output exists.

What worked was converting only the outputs older than the parser:

```python
code = max(os.path.getmtime(f"packages/legal_ingest/{m}.py") for m in ("calibrate", "pagemodel"))
stale = [p for p in glob.glob(f"{out}/*.json") if os.path.getmtime(p) < code]
```

Two source files need care in any such loop: Customs Rules 2001 and The Finance
(Supplementary) Act 2022 are PDFs **with no `.pdf` extension**, so a `**/*.pdf` glob misses
them silently. Logged as a follow-up rather than built: if a third round is interrupted,
`convert_all.py` should grow a resume that compares output mtime against the parser's.

## The register

| invariant | acts | rules | ordinance | total | was |
|---|---|---|---|---|---|
| `section_carries_its_body` | 10 | **8** | 5 | **23** | 32 |
| `no_foreign_section_start_in_body` | 1 | **1** | — | **2** | 4 |
| `section_codes_ordered` | 4 | — | — | 4 | 4 |
| `no_chapter_caption_in_section_heading` | 3 | — | — | 3 | 3 |
| `clause_codes_plausible` | 1 | — | — | 1 | 1 |
| **per lane** | **19** | **9** | **5** | **33** | 44 |

## Verified

- `ruff check` bare — clean · `pytest tools/tests -q` — 58 passed, 1 skipped
- the lock fails with the old positional fallback restored; `__pycache__` cleared after
- conservation **56/56** within gate (customs 20, salestax 19, excise 17)
- `discover_corpus.py --check` — no drift; `signatures.json` unchanged
- documents **80 / 11 / 12**, held · `data/ocr_cache` **0 B**
- rollback: `output/_pre_r10/`

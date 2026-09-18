# Round 43 — sizing q4, and why it is not a rider

**Row q4** says, in its own words: *"Size the blast radius before writing any of it."* This
round does that and **ships no parser change**. `packages/` is byte-identical to `main`.

The answer is **326 rejected header sites across 59 documents**, of which **213 across 51
documents** survive a deliberately strict positive test. q4 is not a rider on anything; it is
a round the size of round 39 or larger, and it needs two changes rather than one.

## The trace, re-derived

Federal Excise Act, 2005 (30-06-2025), PDF page 90, as the parser reads it:

```
top=128.6  x0=256.4  'THIRD SCHEDULE'
top=141.4  x0=249.7  '(Conditional exemptions)'
top=154.0  x0=229.8  '[ See Sub-section (1) of section 16]'
top=172.4  x0=283.4  'TABLE-I'
top=185.0  x0=288.1  '(Goods)'
top=204.6  x0=132.6  'S.No. Description of Goods Heading/'      ← header, 3 columns fused
top=217.2  x0=419.0  'sub-heading'                              ← col-3 header, wrapped
top=229.9  x0=428.2  'Number'                                   ← col-3 header, wrapped
top=255.2  x0=138.7  '(1) Crude vegetable oil, if obtained from the locally 5.07, 15.08,'
top=267.9  x0=175.1  'grown seeds excluding cooking oil, without 15.09, 15010,'
top=280.5  x0=175.1  'having undergone any process other than the 15.11, 15.12,'
```

The row's reading is exactly right: **there is no numbering row**, and the `(1)` on the next
line is a *serial*, not a column label. Column left edges are recoverable from the data —
**138.7 / 175.1 / 409.6** — but not from a numbering row, because none is printed.

It renders today as prose, and the two columns interleave line by line inside an
`<ol class="subsection">`, because `(1)` was read as a subsection marker:

```html
<li>(1) Crude vegetable oil, if obtained from the locally 5.07, 15.08, grown seeds
excluding cooking oil, without 15.09, 15010, having undergone any process other than
the 15.11, 15.12, process of washing. 15.13, 15.14 15.15, 15.16, 15.17 &amp; 15.18
```

That leaf carries **0 `<table>` and 21 `<p>`**.

## It is two changes, not one

The row names the first: `find_table_spans` requires a numbering row within 8 lines of the
header start, and refuses the span otherwise.

**The second is not in the row, and it is on the same document.** Once a span *is* accepted,
the extension loop ends the table on a `(N)` line that is not a numbering row:

```python
if _NUM_TOKEN.match(w[0].text.strip()) and not _is_numbering_row(w):
    break
```

`_NUM_TOKEN` is `^(?:Col\.?\s*)?\(\d+\)$`, and it matches `(1)` and `(2)` — *the Third
Schedule's serials*. So the same spelling that makes the column count unrecoverable would
also terminate the span at its **first data row**. Relaxing the numbering-row requirement
alone yields a one-row table.

## The blast radius

Every `_is_header_start` line in the corpus, counted against whether a numbering row follows
within 8 lines, over the **143 acts and rules sources** (2 non-PDF entries error out):

| | count | documents |
|---|---|---|
| **accepted** today (numbering row present) | **836** | — |
| **rejected** today (none within 8 lines) | **326** | **59** |
| — of which `S.No.`-style headers | 286 | |
| — of which the bare keyword `TABLE` | 40 | |
| rejected, by lane | acts 170 / rules 156 | |

**326 is the population any relaxation admits.** It is not a small tail: it is 28% of all
header starts in the corpus.

### A strict positive test barely narrows it

Not every reject is a table. Classifying all 326 by the structure a column-inference fallback
would actually have to read — the header line's own x0 clusters, and how many of the next 8
lines carry more than one cluster:

| header x0-clusters | sites |
|---|---|
| ≥ 3 | **257** |
| 2 | 19 |
| ≤ 1 | 50 |

Requiring **≥3 header columns AND ≥4 of the next 8 lines carrying columns** — a test meant to
exclude prose — still leaves:

> **213 sites across 51 documents.**

| sites | document |
|---|---|
| 31 | Customs Rules, 2001 (30.06.2023) |
| 11 | Finance Act, 2021 |
| 11 | Federal Excise Act, 2005 (31 Dec) |
| 11 | Federal Excise Act, 2005 (15-01-2022) |
| 11 | Federal Excise Act, 2005 (30-06-2020) |
| 11 | Federal Excise Act, 2005 (30-06-2021) |
| 11 | Federal Excise Act, 2005 (30 June) |
| 6 | Sales Tax Rules 2006 (30 June 2015) |

For comparison, **round 39's `Col.(N)` change moved 17 documents** and needed a two-pass
conversion of 119 sources to measure. This is **three times that reach**, on a change with
*no numbering row to validate the recovered column count against*.

### The rejects are genuinely mixed

Real tables that simply print no numbering row:

```
S.No. Petroleum Products Unit Maximum Petroleum      (Finance Act 2018-19, p1)
TABLE / Tax Year Rate of Tax / 2019 29%              (Finance Act 2018-19, p93)
S.No. Nature of assets Amount in Tax Tax in Pak      (Finance Act 2018-19, p143)
```

Prose that merely begins with the header spelling:

```
S. No. and the entries relating thereto in columns (2), (3)
and (4), shall be added, namely:-                    (Finance Act 2024, p35)

Table / Procedure and conditions:- / (1) The sales tax on account of
minimum value addition ...                           (Finance Act 2019, p65)
```

And double counts — a bare `TABLE` line and the `S.No.` header beneath it are two rejects for
one table (40 of the 326 are the bare keyword).

## Recommendation

**Do not take q4 as a rider, and do not relax the numbering-row requirement.** The staging
that the measurements support:

1. **Infer columns from the DATA's left-edge clusters, not the header's.** On the target
   document the header's clusters (132.6 / …) do not align with the data's (138.7 / 175.1 /
   409.6); the header wraps its third column over two further lines. The row offers both
   sources and the data is the reliable one.
2. **Fix the `(N)` terminator in the same change**, or the span ends at row 1.
3. **Budget a round-39-scale measurement**: two conversions of the convertible corpus, a
   per-document gained/lost table, and `plain_text` compared with whitespace removed. 51
   documents is the expected reach, not 1.
4. **Expect the census to be the gate.** There is no invariant for "this table rendered as
   prose"; round 39's evidence was a `<tr>`/`<p>` diff, and this needs the same.

## What this round changes

Nothing in `packages/`. It converts q4 from *open and unsized* to *open and sized*, with the
second defect (`_NUM_TOKEN` terminating on the serial) recorded, which the row did not have.

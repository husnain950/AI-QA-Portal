# Phase 3 round 12 — the heading stripper that ignored the code it was handed

Two blind spots, one defect class, and a register that does not move.

## What was actually wrong

`packages/legal_ingest/builder.py`

```python
def _body_heading_title(h4_inner: str, code: str) -> str:
```

**`code` was never referenced in the function body.** The strip ran off
`_HEAD_CODE_PREFIX_RE`, built on `grammar.CODE`:

```python
CODE = r"\d{1,4}-?[A-Z]{0,4}"     # tolerates a HYPHEN, never a SPACE
```

Two real families print their code with a space in the text layer. `builder.py`
already knows this — `_DOTSUFFIX_RE`'s own comment says "the separator may be a
HYPHEN or a SPACE but never a DOT", and `_candidate_code` folds `150 ZQR` →
`150ZQR` so the TOC and body sides agree on one spelling. The *detector* handled
the split code. The *heading stripper* did not:

| printed body line | code minted | heading emitted |
|---|---|---|
| `150 ZQT. Goods to be monitored electronically…` | `150ZQT` | `ZQT. Goods to be monitored electronically…` |
| `156 A. Proceedings against authority and persons` | `156A` | `A. Proceedings against authority and persons` |
| `25 AA. Transactions between associates` | `25AA` | `AA. Transactions between associates` |
| `37 D. Cognizance of offences by Special Judges` | `37D` | `D. Cognizance of offences by Special Judges` |
| `14 A. Credit and debit notes` | `14A` | `A. Credit and debit notes` |
| `18 A Special customs duty on imported goods` | `18A` | `A Special customs duty on imported goods` |

Two normalisers disagreeing about one spelling — the same shape as round 1's
chapter numeral, and round 9's TOC-vs-body code fold.

## The fix was already in the repo

`discover._heading_from_words` solves this exact disagreement and says why:

```python
# The code arrives FOLDED (``_candidate_code`` canonicalises it), but the
# words here carry the PRINTED spelling -- "193-A", "25 AA", "18.A".
txt = re.sub(r"^\(?" + r"[\s.\-]*".join(map(re.escape, code)) + r"\)?\s*\.?\s*", "", txt)
```

`_body_heading_title` now drives its strip from the code it is already passed,
the same way — but **the longest match wins**, and neither pattern could be
dropped. Two measurements forced that, both found by re-converting and diffing
rather than by reasoning:

- **The code-driven pattern alone strips too little.** Where the body prints a
  suffix the TOC's code lacks (`15A. Title` under code `15`), it matches the
  digits and leaves `A.` behind — reintroducing the very shape being removed.
  The positional pattern spans it. It also cannot match at all where the body
  prints a different code than the TOC lists (Sales Tax Rules lists `39E` for a
  body printing `39K` with the same title), where positional is still right.
- **The separator run must not swallow the code's own terminator.** The first
  attempt regressed Customs `193A`, whose body prints `193. Appeals to
  Collector`: `3` + `. ` + `A` matched, and the heading came out as `ppeals to
  Collector`. `discover._heading_from_words` carries the same construction and a
  comment claiming its `len(code)-1` bound makes this impossible — the bound
  limits how *many* separator runs there are, not how far one reaches, so it does
  not hold for a code whose letter suffix also begins the title word. The code
  token now has to end on a boundary, which makes that case fall through to
  positional — the right answer there.

Each pattern covers the other's blind spot and both are anchored, so taking the
longer span can never strip less than today does.

## Measured

**31 leaves, 15 documents, 2 lanes, one cause.** Every one had
`heading_source="body"`; a TOC-sourced heading is clean, which is why a section
only shows the defect once it *has* a body to be read from.

| lane | before | after | codes |
|---|---|---|---|
| rules | 17 | **0** | the 16-rule `150ZQ*` run (Sales Tax Rules 01-01-2025), `14A` (Federal Excise 10.07.2014) |
| acts | 14 | **0** | `156A` × 7 editions, `18A` × 5 editions, `25AA`, `37D` |
| ordinance | 0 | 0 | separate `fbr_ingest` fork, does not run this |

The count opened at 26 and closed at 31: the first census required the code tail
to carry a dot, and Customs `18A` prints it without one — `A Special customs duty
on imported goods`. Widening the invariant to make the dot optional was measured
before it was adopted: it finds those 5, and reports **0 across both lanes on the
fixed corpus**, so it costs nothing here. The residual risk it accepts is a title
that genuinely begins with the article "A" under a code ending in A; none exists
in this corpus, and the suffix test keeps every other capitalised opening out.

Conservation: **zero `plain_text` delta** on every affected document, and
identical leaf counts. The fix moves characters out of the `heading` field and
touches nothing else — which is the whole claim, and the thing worth checking,
since a strip that reached one character too far would eat a title word.

## Why no invariant saw it

Two independent blind spots, both closed here.

### 1. The register could not see a failing regression case

`tools/tests/test_register_snapshot.py` is what gates the pipeline on CI, because
`data/corpora/*/output/` is gitignored and the lane suites SKIP there. It parsed
the suite output with

```python
_FAIL = re.compile(r"\[ *FAIL \((\d+)\)\] +([a-z_]+)")
```

That matches `[ FAIL (3)] section_carries_its_body` — an **invariant**, which
carries a count. It never matched `[FAIL] <case_id>` — a **regression case**,
which is pass/fail. Cases are this project's locking mechanism: every fix ships
pinned by one in the same PR. So for as long as the register has gated CI, the
mechanism protecting every fix already made was gated by nothing, and **two cases
were failing** when this round opened.

The register is a count of known-open defects and moves deliberately, so it gets
a committed snapshot. A case is the opposite — its only correct value is zero —
so it gets an assertion, not a snapshot. Both readings now come from one suite
run per lane rather than two.

### 2. A case scoped by date matched the wrong document

Round 11's lock case carried `"applies_to": "as amended up to 30.06.2021"`, and
`runner.py` treats `applies_to` as a **substring of `metadata.filename`**. The
acts lane holds two documents matching that date:

- `Sales Tax Act, 1990 as amended up to 30.06.2021` — intended, passes
- `Customs Act, 1969 as amended up to 30.06.2021` — collateral, has no s.73, fails

So the round-11 lock was reporting a failure on a document it was never about.
Now scoped to `"Sales Tax Act, 1990 as amended up to 30.06.2021"`, which selects
exactly one.

Every other scoped case was swept for the same collision. Two match multiple
documents and both are deliberate — `o05_sec9_interior_endash_not_a_terminator`
(20 Customs editions) and `fe_r78_double_hyphen_heading_keeps_body` (2 Federal
Excise editions), all passing. None matches zero documents.

## The new invariant

`no_code_fragment_in_section_heading` — a section heading must not open with the
tail of its **own** code.

The test is deliberately not "looks like a code": that would report a rule whose
title genuinely begins `A.`. It is that the leftover token is a **proper suffix
of the leaf's own `code`**, which no real title is. Self-validating, and it needs
nothing from outside the leaf — unlike the cross-edition sibling count that round
11's blindness still wants, and unlike the "no chapter may be empty" idea that
round 11 measured and rejected (it fired on 29 of 103 documents, most of them
legitimately empty chapters).

Measured **alone, on unchanged JSON**, before the parser fix: 31 hits, matching
an independent census exactly. After the fix: 0.

## Register

Unchanged at **30**. The 31 were invisible to every invariant the suite had, and
the invariant that can see them closes at zero in the same PR. This round's
number is 31 headings repaired and two gates that could not fail — reported
rather than folded into a total, per the rule the project already follows for
changes that move the register by zero.

## Locked by

- `tools/tests/test_body_heading_code_strip.py` — the printed shapes, the five
  that already worked, the positional fallback, the `193A` terminator case, and
  the bound that stops the strip reaching past the code. Fails two ways with the
  fix reverted.
- `_common._demo_code_fragment_in_heading` — the invariant both ways, including
  the titles that merely look code-shaped.
- `test_no_active_regression_case_fails` — fails on the tree that opened this
  round, naming both cases and the documents they failed on.

# Phase 3 — Sales Tax Act 1990 (01.07.2014) s.10 (acts 1 → 0)

Written 2026-09-14. Branch `fix/phase3-sales-tax-2014-s10`, **stacked on**
`fix/phase3-acts-exemptions`.

Closes the last acts-lane hit by *exemption with evidence*. **The acts lane is now at zero.**

This round is mostly a record of a **fix that was attempted, measured, and rejected**, which
is the more useful half.

---

## What the plan expected, and what the bisect found

The plan for this row said the body pattern was probably fine and the likely cause was the
contents↔body heading comparison — and told the implementer to **bisect, not guess**. Both
guesses were half right.

The body line, PDF page 37: a 7.00pt marker `1`, then the 12.00pt token **`[(10)`** — the
code parenthesised **and** inside an amendment bracket — then `Refund of input tax.` and two
separate U+2013 EN DASH tokens.

Running every section-start pattern in `builder` against it:

| line | matched by |
|---|---|
| `(10) Refund of input tax. – –` | `_PAREN_SECTION_RE` ✅ |
| `[(10) Refund of input tax. – –` | **nothing** |
| `1[(10) Refund of input tax. – –` | **nothing** |

So the bracket is what closes it. `_BRACKETPAREN_RE` is
`_HEAD + rf"\[\s*\(?({CODE_SUFFIXED})\)"` and `CODE_SUFFIXED` is `\d{1,4}-?[A-Z]{1,4}` — it
**requires a letter suffix**.

## That requirement is load-bearing, and its comment says why

> A parenthesised code is only a SECTION when it carries a letter suffix. `CODE` alone
> matched an inserted SUBSECTION — `2 [ (5) The Federal Government may, by notification...`
> on page 40 of the 2007 edition read as section 5, and because it sat 8 pages past section
> 5's real page the tol-8 fallback took it, advanced the monotonic cursor past pages 32-38
> and blocked **THIRTY** later sections into heading-only stubs.

## The candidate widening was measured and is wrong

The obvious repair is to admit a bare parenthesised code when the line also carries a
**heading terminator dash** — which `[(10) Refund of input tax. – –` has and
`[ (5) The Federal Government may…` has not.

Measured over every acts and rules document, the population of `[(NN)` lines:

| shape | count |
|---|---|
| capitalised title, **no** dash | 1,948 |
| no capital, no dash | 465 |
| **capitalised title, WITH dash** | **83** |
| no capital, with dash | 9 |
| **total** | **2,505** |

The 83 are the problem. They are **section 2's definition clauses**:

```
3[(3) “associates (associated persons)” means, –
5[(21) “person” means,–
1[(44) “time of supply”, in relation to,–
2[(2) Restriction-2 – Brand variants at different price points].–
```

A dash-gated rule would **mint 83 phantom sections inside section 2** to recover one real
section. Rejected.

## And the one remaining discriminator is destroyed by the same edition

If line shape cannot separate a parenthesised section from a parenthesised subsection, the
contents page can: section 10 is listed, expected and unstarted.

It cannot be used here. **PDF page 3 has no ToUnicode mapping for the letter `e`.**
pdfplumber emits the row as `R(cid:2)fund of input tax` — and `not(cid:2)` for "note" on the
same page. The body title `Refund of input tax` matches nothing.

That cid is also why the leaf's heading reads `R(cid:2)fund of input tax`. Per the
convention rounds 21-28 set, a source defect is preserved rather than invented around, and a
`(cid:N)` remap needs a per-font glyph table the conversion path deliberately does not carry.

**Two independent defects in one edition, each closing the route the other leaves open.**
That is what makes this an exemption rather than a deferral.

## Result

| lane | before | after |
|---|---|---|
| **acts** | 1 | **0** |
| rules | 1 | 1 |
| ordinance | 3 | 3 |

No parser code touched, no PDF converted, no expiry (`native-digital`).

`pytest tools/tests -q` 231 passed, 1 skipped · `ruff check` (bare) clean ·
`data/ocr_cache` 0 B.

## If a future round wants to delete this entry

Good. But measure the candidate against those **2,505** lines first, and against the **83**
in particular. The entry says so in its own text.

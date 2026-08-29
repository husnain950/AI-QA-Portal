# Phase 3, class 2 — the apparatus caption was never in the body

Review page: <https://claude.ai/code/artifact/82c89c19-7b68-420e-8ee8-a92131a9ae04>

Follows [`wip/phase3-chapter-numerals.md`](./phase3-chapter-numerals.md) (PR #46). Closes
`no_footnote_text_in_body`, the second-largest class on the register, and it decomposes the
way round 1 said to expect: **an invariant that was wrong, and behind it a parser defect
the invariant was not actually measuring.**

## 1. Forty-five hits, none of them in a body

Every one of the 45 hits was `LEGAL REFERENCE caption in body`, on Customs Act sections
79 / 81 / 123 and the SECOND/THIRD SCHEDULE across 20 editions. The message is wrong. The
caption is not in the prose — it is inside a citation tooltip:

```html
<sup class="cite" title="Added by Finance Act, 2015&#10;LEGAL REFERENCE">79.8</sup>
```

`inv_no_footnote_text_in_body` ran `_LEGAL_REF_CAPTION.search(html)` over **raw markup**, so
an attribute counted as body text. Measured over the whole acts lane: **45 of 45** hits are
inside a `title=` attribute; **zero** appear in rendered text, in `plain_text`, or in the
HTML outside the attributes.

The invariant now strips tags before searching, using the same
`re.sub(r"<[^>]+>", "", html)` idiom `_common.py` already applies in five other places.

**Measured on identical JSON, that alone is 193 → 148.**

## 2. What the false positive was hiding

A citation tooltip carries the note it points at, so the caption being *in* the tooltip
means the caption was in the **footnote's own text** — a real defect, and a bigger one than
the register showed. `LEGAL REFERENCE` sat in **473 footnote texts across 20 Customs
editions**, against 45 reported hits.

The path was a two-step, and each step was individually reasonable:

1. `build_page_model` found the caption left in `body_lines` by the single Y-cut and moved
   it into `footnote_lines`, so it would not render as a trailing
   `<p><strong>LEGAL REFERENCE</strong></p>` in statutory text.
2. `parse_footnotes` reads `footnote_lines` in order. The caption arrives **before any
   marker**, and a pre-marker line is by definition the tail of a note continued from the
   previous page. So it came back as a `^cont` fragment, and
   `merge_footnote_continuations` spliced it onto the previous page's last note.

A caption printed *above* the notes was appended to the note *before* it, and every leaf
citing that note inherited it.

**The caption belongs in neither zone.** It is not statute and not a note. It is now
dropped from both, whichever side of the cut it landed on — `_drop_apparatus_captions`,
called twice in `build_page_model`.

## 3. The shorter fix was in the wrong place, and the audit said so

The first version of this fix guarded `parse_footnotes` instead: skip a caption line when
building notes, leaving it in `footnote_lines`. It worked — 473 → 0 — and it was wrong.

`tools/acts/audit_completeness.py` compares the page model's `footnote_lines` (source side)
against the output's footnote **texts** (output side). A caption present on the source side
and absent from the output side is, to the audit, lost text:

| Customs 11.03.2019 | body | footnotes |
|---|---|---|
| before this PR | 100.000%, 0 missing | 100.000%, 0 missing |
| guard in `parse_footnotes` | 100.000%, 0 missing | **99.775%, 48 missing** |
| drop in `build_page_model` | 100.000%, 0 missing | 100.000%, 0 missing |

The 48 were `LEGAL: 24, REFERENCE: 21, REFERENCES: 2, REFERENCS: 1` — the caption itself, in
all three printed spellings. Dropping it one layer earlier costs nothing on either side and
is the shorter diff: it replaces the move-between-zones block rather than adding to it.

That measurement is the only reason the right layer was chosen, and it is why the fix is
locked at the seam it actually lives on (`_drop_apparatus_captions`) rather than at
`parse_footnotes`, where the earlier version's test would still have passed.

## 4. A stale gap that had no way to say so

`inv_no_footnote_text_in_body` carried a hardcoded skip for one (edition, leaf) pair:
Income Tax Ordinance 11.03.2019, Division XXI, whose substituted rate table used to render
inside the division body.

Re-measured: that leaf matches **no branch** of the check — no marker text, no caption, in
neither `plain_text` nor `html`, before this PR as well as after. The gap had been closed by
earlier work and nothing noticed, because **a skip hardcoded inside a check function cannot
report itself as stale**. An entry in `tools/suite/exemptions/` does exactly that: the
runner prints `exemption is now stale -- delete the entry` the moment its invariant starts
passing.

Deleted rather than moved to `exemptions/ordinance.json`, because there is nothing left to
exempt.

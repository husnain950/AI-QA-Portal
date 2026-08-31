# The pipeline output contract

`data/corpora/<lane>/output/*.json` is the boundary between the pipeline and the QA
portal. Everything downstream — `sync_acts`, `document_versions`, the review page — is
built on what a file at that path guarantees. This document is that guarantee.

It is enforced, not described: `contract_complete` in
`tools/suite/invariants/_common.py` fails a document that claims a contract version and
does not meet it, and the code that stamps it lives in one place,
`packages/legal_contract.py`, so both pipelines emit the same shape.

`docs/pipeline-readme.md` is the *ordinance* pipeline's own history and internals. It
predates this contract and describes one lane. Where the two disagree, this file wins.

---

## Structure

```
{
  "metadata":  { ... },
  "preamble":  { "html": str, "plain_text": str }         # optional
  "chapters":  [ container, ... ],
  "schedules": [ container, ... ]
}
```

A **container** nests `parts[]`, `divisions[]` and `sections[]`. A **leaf** is any node
carrying `html`. Containers may also be leaves: `rvw_export` emits leaf-shaped parts
under chapters for gazette continuations, and the portal's flattener allows it.

Every node — container and leaf alike — carries `code`, `type` and `node_key`.
A leaf additionally carries `heading`, `html`, `plain_text`, `start_page`, `end_page`,
`page_number` and `footnotes[]`.

## Metadata

**Required of every document.** Absence is a contract violation.

| key | meaning |
|---|---|
| `contract_version` | integer. The version of *this* document. See [Versioning](#versioning). |
| `filename` | the source PDF's basename. `sync_acts` resolves the PDF by exact match on it. |
| `total_pages` | pages in the source PDF |
| `chapters_count`, `schedules_count`, `sections_count` | counts, for a cheap cross-check |

**Required of a document a conversion produced.** `tools/convert.py` stamps these; they
are what makes two runs distinguishable. A file without them was not written by a
conversion — a fixture, or a direct `run()` call — which is legitimate, so the suite does
not require them and the sync does.

| key | meaning |
|---|---|
| `lane` | `acts`, `rules` or `ordinance` |
| `pipeline_revision` | short git sha of the converting tree, `-dirty` if it was, `unknown` if there was no git |
| `converted_at` | ISO-8601 UTC, second precision, `Z`-suffixed |

**Optional. A consumer must tolerate absence of every one of these**, because they come
from stages that not every document goes through:

`family`, `family_confidence`, `instrument_kind`, `amends`, `notified_by`, `source_kind`,
`calibration`, `ocr`, `toc_pages_scanned`, `body_chapter_numerals`.

## Identity

Every node carries:

- **`type`** — one of `chapter`, `part`, `division`, `schedule`, `section`. Before this
  existed, the output used one dict shape for a chapter, a schedule part and a section
  leaf, and a consumer had to infer the kind from which keys happened to be present.
- **`node_key`** — the ancestor chain **by code**: `ch:vii/pt:i/s:114`. Not by array
  index.

`node_key` grammar:

```
node_key   := segment ("/" segment)*
segment    := abbrev ":" slug ("~" ordinal)?
abbrev     := ch | pt | dv | sch | s
slug       := the node's code, lowercased, leading kind-word stripped, spaces to hyphens
              "CHAPTER XIV-A" -> "xiv-a"    "114A" -> "114a"    "Schedule II" -> "ii"
              "FIRST SCHEDULE" -> "first-schedule"   (the word is not leading)
              ""  ->  "~root"   (the synthetic container a flat act gets)
ordinal    := 2, 3, ...   appended when a sibling code repeats
```

### What is guaranteed

**Stable across reprocessing.** A leaf whose position in the *legal* hierarchy has not
changed keeps its `node_key`, however the document is re-parsed and whatever is inserted
above or below it. This is the whole point: the positional `source_key` the portal mints
(`/chapters/0/sections/3`) renames every later sibling when one leaf is inserted —
measured at **386 leaves falsely reported "changed"** across 84 documents from a single
insertion each, with 16 documents churning 100% of themselves. On `node_key` the same
test reports 0.

**Unique within a document.** Measured at 0 collisions across all 11,504 keys on disk,
and locked by `contract_complete` on *every* document, including ones that predate the
contract. A collision is not cosmetic: it merges two leaves' review state into whichever
the walk reaches last.

### What is NOT guaranteed

**Stability across editions.** `ch:vii/pt:i/s:114` in the 2024 edition and the same key
in the 2025 edition are the same *citation*, not the same reviewed unit. Cross-edition
identity is `section_variants`' job (`apps/api/backend/services/variants.py`). Do not use
`node_key` to join editions.

**Stability across a code change.** A leaf whose own code or an ancestor's code changes
gets a new key. That is correct — a renumbered section is a different provision — and the
portal treats it as a removal plus an addition, orphaning annotations with a snapshot.

**Meaning.** A `node_key` is an identifier. Do not parse it to recover hierarchy for
display; the flattened `chapter_code` / `part_code` / `division_code` fields are the
denormalisation for that, and the tree is the source.

## Ordering

Reading order is currently **derived by the consumer**, not stated by the contract:
`json_parser._apply_reading_order` sorts leaves by `start_page`, stably, so leaves on one
page keep tree order.

This is a known gap, deliberately left open rather than guessed at. Measured, tree-walk
order and page-sort order disagree on **21 of 103 documents**, and on some of them
heavily — 222 of 327 positions in Sales Tax Rules 2006, 62 of 62 in Customs Rules 2001.
Which order is *right* cannot be settled from the JSON; it needs the source pages. Until
it is settled, the contract states the rule that is actually in force rather than a field
nobody mints.

Consumers must therefore sort by `start_page` and must not rely on array order.

## Reprocessing

- **Byte-identical JSON** ⇒ no new version, no row writes, no events.
  (`versions.create_version` compares `json_sha256` against the active version.)
- **Changed JSON** ⇒ exactly one new `document_versions` row, made active. Leaves are
  matched by `node_key`; the `carryover` report on that row is the complete account of
  what human review state moved, was reset, or was orphaned.
- Re-running a conversion over an unchanged PDF with an unchanged parser must produce
  byte-identical JSON apart from `converted_at`. Anything else is non-determinism and a
  defect.

## Deletion

- A **leaf** present in version *n* and absent in *n+1* is removed. Its annotations are
  detached and marked `orphaned` with a snapshot of the text they were made against —
  never deleted.
- A **document** whose JSON leaves `output/` is *withdrawn*, not deleted.

## Partial failure

- One unparseable document fails alone. The run reports it under `problems[]` and exits
  non-zero; the other documents still sync. `--strict` restores all-or-nothing for CI.
- A truncated or unparseable JSON is a hard failure, never a silently empty document.
- A conversion writes through a temporary file and renames, so `output/*.json` never
  contains a partially written document. A killed converter leaves the previous
  conversion intact.

## Versioning

`contract_version` is an integer on the document.

- **Adding an optional key is not a bump.** Consumers must already tolerate unknown keys.
- **Changing or removing a key, or changing what one means, is a bump.**
- A document with no `contract_version` predates the contract (version 0 by implication).
  It is still ingestible: the portal falls back to `source_key` matching for its leaves.
  That fallback is the contract's only backwards-compatibility affordance, and it is
  deleted once no document relies on it.

Current version: **1**.

## Where each rule lives

| rule | enforced by |
|---|---|
| identity and required metadata | `tools/suite/invariants/_common.py::inv_contract_complete` |
| `node_key` uniqueness | the same, on every document |
| stamping | `packages/legal_contract.py`, called by both pipelines |
| run provenance | `tools/convert.py`, the only writer |
| atomicity | `tools/convert.py`, tmp + `os.replace` |
| the self-check | `packages/legal_contract.py::_demo`, run by `tools/run_tests_smoke.py` |

# Round 47 — a narrow corpus sync, and what the local database actually holds

Round 46 found **two Federal Excise editions still at round 38** and fixed them in
`output/`. Getting just those two into the portal was the next step, and the handover
note warned that a blanket `sync_corpus.py` would create **75 provenance-only versions**
alongside the 2 real ones, because round 46's restamp changed every staged file's bytes.

Two things came out of measuring that before running it. The first is a trap in the
obvious workaround. The second is that the premise was wrong.

## The trap: narrowing the corpus directory withdraws the rest of it

The natural way to sync two documents is to point the sync at a directory holding only
those two — `tools/sync_corpus.py --only acts --acts <two-document-root>`, exactly the
override `make seed-fixtures` uses.

`corpus_sync.run_corpus_sync` then calls `reconcile_corpus(label, part["source_keys"])`,
and `reconcile_corpus` withdraws every document of that origin whose stem is **not** in
the listing it is handed:

> `output/*.json` IS the corpus, so a stem that is no longer in it is no longer part of
> it.

Which is correct — for a real corpus root. Handed a deliberately narrowed one it
withdraws **64 acts documents** to install 2. Withdrawal is a timestamp rather than a
delete, so it is recoverable, but it is not what anyone syncing two editions means.

`--match` narrows the **work** instead. `source_keys` is captured from the full
`output/` listing before the filter runs, so reconciliation still sees the whole corpus
and withdraws nothing:

```
tools/sync_corpus.py --only acts --match "11th March 2019"
tools/sync_corpus.py --only acts --match "31st December, 2019"
```

The guard is mutation-tested against both ways it can fail —
`test_match_narrows_the_work_but_not_the_corpus_listing`:

| mutation | result |
|---|---|
| filter `source_keys` as well as the pairs (the withdrawal defect) | **fails** on the listing assertion |
| ignore `match` entirely | **fails** on `matched` / `problems` |

## The premise: there are no provenance-only versions to avoid

The warning assumed the local database already held round 46's content for 75 of the 77,
so a blanket sync would add versions that said nothing. It does not.

Comparing each staged JSON against the JSON blob the local database currently serves,
with `pipeline_revision` / `converted_at` normalised away — the same normalisation that
reproduces round 46's 2-document finding exactly (89 identical, 2 differ against
`_pre_46`):

| | documents |
|---|---|
| staged, convertible | 77 |
| **content differs from the database** | **77** |
| provenance-only drift | **0** |
| identical (the 14 image-backed, never converted) | 14 |

The database predates round 39. A blanket sync would not create 75 empty versions — it
would install **rounds 39-46 across the entire acts and rules corpus at once**, which is
a different decision, and a much larger one, than the note assumed.

Local sign-off state cannot be lost to it either: all 116 rows are `signoff_stage =
draft` and **none** carries a `signoff_reviewed_by` or `signoff_legal_by`.

## Where the review state actually is

`create_version` resets `signoff_stage` to `draft` and clears both sign-off columns on
every version it writes. That cost is zero locally, by the measurement above. It is not
necessarily zero on the deployed portal, which is where the QA cycle was run
(`p01--crx-web…/review/cb324fb0…`) and which this checkout cannot query.

The deployment is fed by `backend.push_corpus`, which walks the **local** database and
re-sends documents whose content hash drifted from the remote's. It has no name filter
and needs none: it sends what the local database holds. So the local database is the
control surface — a narrow sync keeps a push narrow, and a blanket sync makes the next
push a 77-document bulk change to a corpus under legal review.

## FS-02 / FS-07 are unaffected

Both tracker rows are scoped to one document — `Leaf 74 of 81` and `Leaf 75 of 81`,
FIRST SCHEDULE Table-I and Table-II. **81 leaves identifies `Federal Excise Act, 2005 as
amended upto 30-06-2025` uniquely** among the 17 staged editions, which corroborates
round 38's eleven-page-number fingerprint. That edition was among round 45's 15.

The two editions round 46 found carry **69** and **72** leaves, and appear in `_pre_46`
but not in `_pre_45` — they are not the retest subject. The 15-of-17 install gap does not
reach FS-02 or FS-07; it is a separate, un-logged defect in two other editions.

## Verification

```
ruff check                          All checks passed!
pytest apps/api/backend/tests tools/tests -q    879 passed, 3 skipped
run_tests_smoke.py                  Pipeline gate passed (exit 0)
```

The lane suites SKIP in this worktree — the corpus is staged in the main checkout only.
This change touches no pipeline code: `run_sync` gains one filter, and `corpus_sync` and
`tools/sync_corpus.py` pass it through.

**Not done here:** no sync was run, in either direction. The choice between the narrow
two and installing rounds 39-46 wholesale is the corpus owner's.

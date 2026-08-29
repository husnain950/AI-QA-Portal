# Phase 2, measured before it was run

Phase 1 (PR #43) put a working OCR stack on this host, which is the last thing
[`wip/tasks.md`](./tasks.md) said was blocking Phase 2: re-convert `acts` and `rules` at
one parser revision with `--profile auto`.

That run costs **2,456 OCR pages** and `data/ocr_cache` is 0 B, so none of it is banked
— it is paid in full, once, at the rate `--ocr-batch`'s own help records (0.200 pg/s at
one process; four processes measured **59% worse**). Roughly five hours.

Before spending it, `--profile auto` was measured against the corpus it would rewrite.
**It has two defects that would make the run produce worse output than the
`--profile lane` it replaces** — the same class of bug Phase 1 caught on the ordinance
lane, this time on the two lanes Phase 2 targets. A third finding is a prediction in
`wip/tasks.md` that cannot come true.

Nothing was converted. Nothing was fixed. `data/corpora/` is byte-identical. This file
is the finding, and the two decisions taken on it.

## Baseline, this machine, 2026-08-29

| lane | source files | `output/*.json` | `_provisional/` | OCR pages owed |
|---|---|---|---|---|
| acts | 93 | 80 | 9 | **2,065** across 25 files |
| rules | 48 | **11** | 0 | **391** across 36 files |
| ordinance | 45 | 12 | 0 | not a Phase 2 target |

Both OCR censuses were re-measured today with `convert_all.scan_page_count` over the
whole lane — every page, not sampled — and both match the numbers already in
`wip/tasks.md`.

---

## 1. `--profile auto` throws away the RULES profile — blocker

`packages/legal_ingest/families.py:173` hardcodes `consolidated → profile=ACTS`.
`tools/convert.py --profile auto` passes `profile=None` to `run`, which **overrides**
the `functools.partial(pipeline.run, profile=RULES)` binding at
`packages/rules_ingest/__init__.py:20`. So all 34 consolidated rules documents would
parse as Acts.

ACTS and RULES differ on **12 fields**, every one of them parsing behaviour:

| field | ACTS | RULES |
|---|---|---|
| `instrument_kind` | `None` | `'rules'` |
| `ordinal_gap_max` | 1.0 | 2.5 |
| `ordinal_dtop_max` | 2.5 | 6.0 |
| `reattach_raised_ordinals` | False | True |
| `folio_parenthesised` | False | True |
| `folio_running_title` | False | True |
| `subchapter_rows` | False | True |
| `toc_hyphen_leaders` | False | True |
| `toc_codeless_rows` | False | True |
| `toc_tail_density_floor` | `None` | 0.2 |
| `notifying_sro` | False | True |

`tools/discover_corpus.py --verify-lanes` is the check that exists to catch exactly
this, and it cannot see it: at line 412 it `continue`s on `family == "consolidated"`, on
the stated assumption that "acts and rules both parse as consolidated statutes".

`wip/plan.md` records that same claim being corrected in `profiles.py`'s docstring
during Phase 0. It survived here — and in `families.py` it is not a docstring, it is the
routing. This is also why Phase 0's "73 of 190 documents route differently" count
contains **not a single rules document**: the check that produced it skips the family
every rules document is in.

**Reproduce:**

```bash
.venv/bin/python -c "import dataclasses,sys; sys.path.insert(0,'packages'); \
  from legal_ingest.profiles import ACTS,RULES; a,r=map(dataclasses.asdict,(ACTS,RULES)); \
  print([k for k in a if a[k]!=r[k]])"
```

## 2. `--profile auto` quarantines two valid acts documents — blocker

`no_text_layer` carries `profile=None`, so `pipeline.py:358` raises
`refusing …: no_text_layer is not parseable` **before OCR runs** — `signature.measure`
is `pdftotext -layout` only, by design. That refusal reason does not match
`convert_all._ENV_FAILURE_RE`, so `_quarantine` moves the document's previous output
into `output/_refused/`.

Four acts documents in a refused family already have JSON, produced by the lane path:

| document | where | OCR result |
|---|---|---|
| Benami Transactions (Prohibition) Act, 2017 | `output/` | 26/26 pages OCR'd, **85.2%** agreement |
| Income Tax (Third Amendment) Act, 2016 | `output/` | 9/9 pages OCR'd, **87.25%** agreement |
| Income Tax Amendment Act, 2016 | `_provisional/` | below floor — correctly placed |
| Right of Access to Information Act, 2017 | `_provisional/` | below floor — correctly placed |

`ocr.AGREEMENT_FLOOR` is 85.0 (`packages/legal_ingest/ocr.py:57`), so the first two are
above it and are shipping today. The other two show the post-OCR gate already sorting
this population correctly on its own. Rules and ordinance have **0** documents in this
position — it is an acts-only exposure.

> **Decision: `no_text_layer` stays refused, and the loss is accepted.**
> When Phase 2 runs, the acts corpus goes **80 → 78** and those two files move to
> `output/_refused/`. Recorded here so the drop reads as intended rather than as a
> regression, and so whoever runs Phase 2 does not re-open it as a bug.

## 3. Re-conversion cannot move a document out of `no_text_layer`

`wip/tasks.md:166-170` predicts that after re-conversion "most of the 30
`no_text_layer` documents should stop being `no_text_layer`", and asks for the
`signatures.json` diff to be reviewed on that basis.

They cannot move. `signature.measure` reads **the PDF**, and OCR output is written to
`data/ocr_cache` — never back into the PDF. A re-run of `discover_corpus.py --write`
therefore measures the identical text layer and returns the identical family, for all
30.

Inverted: the signatures diff after Phase 2 should be **empty**, and a non-empty one is
a finding rather than the expected outcome.

## 4. The backup Phase 2 owes is the JSON, not the database

`wip/tasks.md:155` asks for `make backup-remote BASE_URL=<prod>` and a local `pg_dump`
first, on the grounds that re-parsing resets sign-off.

Phase 2 runs no `make sync`, so it never reaches the database. (The Docker daemon is
down on this host in any case, so neither command can run — same state Phase 1
recorded.) The sign-off risk is real but it belongs to Phase 4, which is what syncs.

What Phase 2 actually puts at risk is the **91 on-disk JSONs the run overwrites**,
120 MB. The snapshot belongs at `output/_pre_phase2/`: a subdirectory is invisible to
the `output/*.json` glob that defines the corpus (`tools/run_suite.py:39`), which is
exactly why `_refused/` and `_run/` already live there.

It is also the only usable before/after baseline. Per the standing note that the
committed corpus JSON lags `main`, `output/*.json` is not a baseline for a pipeline
change — but a snapshot taken immediately before the run is.

## 5. `--skip-existing` is a resume flag, not a first-pass flag

`wip/tasks.md:163-164` says to use `--skip-existing` on the acts run so an interrupted
run resumes. On a **first** pass it skips precisely the 80 files whose revision this
phase exists to unify (`convert_all.py:510` drops every target whose output already
exists), which is the opposite of the phase's purpose.

Correct usage: run without it; if the run is interrupted, re-run the same command
**with** it, and it picks up only what that pass had not yet written.

## 6. The default `--timeout` is too tight for the acts run

`--timeout` defaults to 5400 s (~90 min) per file. Finance Act 2017-18 alone is **683
OCR pages** — about 57 minutes of recognition at the measured rate — before a ~950-page
document is parsed. The next four are 290, 236, 215 and 148 pages.

The acts run needs `--timeout 10800`. Rules is comfortable at the default: its largest
is 46 pages.

## 7. The provisional lane goes stale unless it is rebuilt

`output/_provisional/` holds 9 below-floor acts documents that an ordinary run does not
produce, so without `--admit-below-floor` they keep whatever revision last wrote them —
the exact staleness Phase 2 exists to remove.

> **Decision: rebuild them in a third short pass alongside the acts run**, so the whole
> acts lane sits at one parser revision.

## 8. What Phase 2 actually buys, per lane

- **rules** — the win is Phase 1's numpy fix, not profiles. Every one of its 48
  documents classifies as `consolidated`, `no_text_layer` or `urdu`; **zero are
  amending**, so `--profile auto` changes no routing on this lane at all. It goes
  11 → ~34 documents, restoring every Income Tax Rules 2002 and Sales Tax Rules 2006
  edition — the lane's entire consolidated backbone.
- **acts** — the 25 amending instruments getting the AMENDING profile is the real
  payload of `--profile auto`, and the only place it earns its name.
- **ordinance** — out of scope. `fbr_ingest.run` takes no profile, and Phase 1's guard
  refuses the run rather than letting 45 children fail and quarantine the lane's 12
  JSONs. Phase 4 decides it.

---

## What this means for the order of work

Findings 1 and 2 are both `--profile auto` being **worse than `--profile lane` on a lane
it was never exercised against**. Phase 0 verified the suites at `HEAD` without
re-converting anything, which is why neither surfaced then. Phase 4 is scheduled to make
`--profile auto` the default.

So the OCR marathon is not the first thing Phase 2 owes. Whenever it resumes, the order
is:

1. Fix finding 1 — a family cannot pick a profile the lane already knows.
   `packages/{acts,rules}_ingest/__init__.py` already export `PROFILE`, and
   `tools/convert.py:72` already imports that module, so the seam exists.
2. Widen `do_verify_lanes` to compare the **resolved** profile rather than skipping
   `consolidated`, so this class of mismatch is a finding next time instead of a
   five-hour surprise.
3. Snapshot to `_pre_phase2/`, then run rules, then acts with `--timeout 10800`, then
   the `--admit-below-floor` pass.

Finding 2 needs no fix — the loss is accepted by decision.

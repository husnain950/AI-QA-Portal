# The measurements behind `plan.md`

Two read-only scripts, stdlib only, run from the repo root against
`data/corpora/*/output/*.json`. They exist because a number quoted in prose cannot tell
you its generator is wrong — the same argument that produced `tools/suite/register.json`.

```sh
python3 wip/integration/measure/census.py   # §3 P2 — identity coverage at the boundary
python3 wip/integration/measure/churn.py    # §3 P1 — false "changed" leaves per insert
```

Neither writes anything. `churn.py` deep-copies before mutating, so the corpus is
untouched.

Both depend on the corpus, which is gitignored — with none staged they print empty
tables rather than failing, exactly as the lane suites skip.

**The corpus revision matters.** Numbers in `plan.md` were measured on the corpus as of
2026-08-31, which is the 2026-08-30 19:54–21:54 conversion (see P11). Nothing in
`metadata` records the parser revision that produced it — that is what PR-A adds.

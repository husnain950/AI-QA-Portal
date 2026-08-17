# Local corpora (gitignored)

Runtime PDFs + pipeline JSON live here so `crx` does not depend on sibling `CC-FBR` paths.

```
data/corpora/ordinance/
  Income Tax Ordinance, 2001/   # source PDFs
  output/                       # converted JSON
  reports/                      # optional pipeline QA reports (--metrics)

data/corpora/acts/
  Acts/                         # source PDFs
  output/                       # converted JSON
  reports/                      # optional
```

Defaults: `CORPUS_ORDINANCE=./data/corpora/ordinance`, `CORPUS_ACTS=./data/corpora/acts`.

These are host-local. A deployed API without these trees on disk is expected: the Library
subtitle reports pipeline-mount health (`output/*.json` present), not whether documents
were uploaded some other way.

Refresh from a sibling CC-FBR tree (optional):

```bash
make vendor-corpora
# or: CC_FBR_ROOT=/path/to/CC-FBR bash tools/bootstrap_corpora.sh
```

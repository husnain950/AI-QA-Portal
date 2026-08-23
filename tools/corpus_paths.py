"""Where the repo, the pipelines and each corpus live -- for the tools under ``tools/``.

The pipeline tools were written for the standalone repositories this monorepo was
assembled from, where a pipeline sat beside its own ``Acts/``, ``output/`` and
``tests/``. Here the code is in ``packages/`` and the corpus is the gitignored
``$CORPUS_<LANE>`` tree, so every one of those tools computed ``_ROOT = crx/tools`` and
then looked for ``crx/tools/output`` -- a directory that has never existed.

The lane list itself is NOT here. It lives in
:mod:`backend.services.corpus_registry`, which the API, the worker and
``tools/sync_corpus.py`` already read. Keeping a second copy is what let this file
drift: its lane table had two entries long after the Rules corpus shipped, so
``$CORPUS_RULES`` was silently ignored and every rules tool resolved to the default
path no matter how it was configured.

What this module still earns its place for is the ``sys.path`` bootstrap below: the
lane scripts are run as ``python tools/<lane>/run_tests.py``, so ``apps/api`` is not
importable until someone puts it there. Doing it once here beats five copies.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: repo root -- this file is at ``<root>/tools/corpus_paths.py``
REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGES = REPO_ROOT / "packages"

for _path in (REPO_ROOT / "apps" / "api", PACKAGES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from backend.services.corpus_registry import (  # noqa: E402 (sys.path bootstrap above)
    CORPORA,
    LABELS,
    Corpus,
    get,
)

__all__ = ["REPO_ROOT", "PACKAGES", "CORPORA", "LABELS", "Corpus", "get",
           "corpus_dir", "output_dir", "source_dir"]


def corpus_dir(lane: str) -> Path:
    """The corpus root for ``lane``, honouring its ``CORPUS_*`` environment variable."""
    return get(lane).path()


def output_dir(lane: str) -> Path:
    """Where a lane's converted JSON lives. This is the glob that defines the corpus."""
    return get(lane).output_path()


def source_dir(lane: str) -> Path:
    """Where a lane's source PDFs live."""
    return get(lane).source_path()


def _demo() -> None:
    import os

    assert PACKAGES.is_dir(), PACKAGES
    assert LABELS == ("ordinance", "acts", "rules"), LABELS
    for lane in LABELS:
        assert output_dir(lane) == corpus_dir(lane) / "output"
        assert corpus_dir(lane).is_absolute()
    # a repo-relative env value must anchor to the repo, not the cwd
    os.environ["CORPUS_ACTS"] = "./data/corpora/acts"
    assert corpus_dir("acts") == REPO_ROOT / "data" / "corpora" / "acts", corpus_dir("acts")
    os.environ["CORPUS_ACTS"] = "/tmp/elsewhere"
    assert corpus_dir("acts") == Path("/tmp/elsewhere"), corpus_dir("acts")
    del os.environ["CORPUS_ACTS"]
    # the lane the old two-entry table silently ignored
    os.environ["CORPUS_RULES"] = "/tmp/rules-elsewhere"
    assert corpus_dir("rules") == Path("/tmp/rules-elsewhere"), corpus_dir("rules")
    del os.environ["CORPUS_RULES"]
    print("corpus_paths self-check passed")


if __name__ == "__main__":
    _demo()

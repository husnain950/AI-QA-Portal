"""Where the repo, the pipelines and each corpus actually live.

The pipeline tools under ``tools/<lane>/`` were written for the standalone
repositories this monorepo was assembled from, where a pipeline sat beside its own
``Acts/``, ``output/`` and ``tests/``. Here the code is in ``packages/`` and the corpus
is the gitignored ``$CORPUS_<LANE>`` tree, so every one of those tools computed
``_ROOT = crx/tools`` and then looked for ``crx/tools/output`` -- a directory that has
never existed. The assumption is resolved in one place so a third lane inherits it
rather than re-deriving it.
"""

from __future__ import annotations

import os
from pathlib import Path

#: repo root -- this file is at ``<root>/tools/corpus_paths.py``
REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGES = REPO_ROOT / "packages"

#: lane -> the environment variable naming its corpus root
CORPUS_ENV = {
    "ordinance": "CORPUS_ORDINANCE",
    "acts": "CORPUS_ACTS",
}


def corpus_dir(lane: str) -> Path:
    """The corpus root for ``lane``, honouring its ``CORPUS_*`` environment variable.

    ``.env`` ships these as repo-relative paths (``./data/corpora/acts``), so a
    relative value is anchored to the repo root rather than the working directory --
    otherwise every one of these tools only works when run from the root.
    """
    env = CORPUS_ENV.get(lane)
    raw = (os.environ.get(env) if env else None) or str(
        REPO_ROOT / "data" / "corpora" / lane
    )
    return REPO_ROOT / raw  # a no-op when raw is already absolute


def output_dir(lane: str) -> Path:
    """Where a lane's converted JSON lives. This is the glob that defines the corpus."""
    return corpus_dir(lane) / "output"


def source_dir(lane: str) -> Path:
    """Where a lane's source PDFs live.

    ``Acts/`` when the corpus has one, else the corpus root -- the same rule
    ``backend.sync_acts._source_pdf_index`` applies, so the converter and the sync
    agree on what counts as a source.
    """
    root = corpus_dir(lane)
    nested = root / "Acts"
    return nested if nested.is_dir() else root


def _demo() -> None:
    assert REPO_ROOT.joinpath("packages").is_dir(), REPO_ROOT
    assert PACKAGES.name == "packages"
    for lane in CORPUS_ENV:
        assert output_dir(lane) == corpus_dir(lane) / "output"
        assert corpus_dir(lane).is_absolute()
    # a repo-relative env value must anchor to the repo, not the cwd
    os.environ["CORPUS_ACTS"] = "./data/corpora/acts"
    assert corpus_dir("acts") == REPO_ROOT / "data" / "corpora" / "acts", corpus_dir("acts")
    os.environ["CORPUS_ACTS"] = "/tmp/elsewhere"
    assert corpus_dir("acts") == Path("/tmp/elsewhere"), corpus_dir("acts")
    del os.environ["CORPUS_ACTS"]
    # an unknown lane still resolves, so a new pipeline works before it has an env var
    assert corpus_dir("rules") == REPO_ROOT / "data" / "corpora" / "rules"
    print("corpus_paths self-check passed")


if __name__ == "__main__":
    _demo()

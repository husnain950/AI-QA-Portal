"""The corpora this platform ingests.

Adding the Rules corpus meant touching a two-element hardcode in eight places:
``corpus_sync`` built ``jobs`` from a literal pair, ``routes.corpus`` declared
``ordinance_*`` and ``acts_*`` fields by hand, ``worker`` passed two paths by keyword,
``tools/sync_corpus`` had two flags, and each of them named the same environment
variables again. The list lives here instead, so a fourth corpus is one entry.

A corpus is a directory holding ``output/*.json`` (the converted documents, which is
what defines the corpus) plus the source PDFs those JSONs name in
``metadata.filename``. It is gitignored and frequently absent -- on CI always, on a
deployment usually -- so "configured" here means *mounted on this host*, never
"documents exist in the database".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional


def _infer_repo_root() -> Path:
    """Host monorepo root, or /app inside the API image (shallower path)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "apps" / "api").is_dir() and (parent / "packages").is_dir():
            return parent
    # Docker: /app/backend/services/this.py → /app
    if len(here.parents) >= 2:
        return here.parents[2]
    return Path.cwd()


REPO_ROOT = _infer_repo_root()


@dataclass(frozen=True)
class Corpus:
    label: str
    env: str
    seed_env: str
    #: Human name for API errors and the Library subtitle.
    title: str

    def path(self) -> Path:
        raw = os.environ.get(self.env)
        if raw:
            return Path(raw).expanduser()
        return REPO_ROOT / "data" / "corpora" / self.label

    def seed_path(self) -> Optional[Path]:
        raw = os.environ.get(self.seed_env)
        return Path(raw).expanduser() if raw else None

    def configured(self) -> bool:
        return corpus_root_configured(self.path())


CORPORA: tuple[Corpus, ...] = (
    Corpus("ordinance", "CORPUS_ORDINANCE", "SEED_CORPUS_ORDINANCE", "Ordinance"),
    Corpus("acts", "CORPUS_ACTS", "SEED_CORPUS_ACTS", "Acts"),
    Corpus("rules", "CORPUS_RULES", "SEED_CORPUS_RULES", "Rules"),
)

LABELS: tuple[str, ...] = tuple(c.label for c in CORPORA)
_BY_LABEL = {c.label: c for c in CORPORA}


def get(label: str) -> Corpus:
    return _BY_LABEL[label]


def corpus_root_configured(path: Optional[Path]) -> bool:
    """True when ``path`` is a usable pipeline corpus (a dir with ``output/*.json``).

    This is mount health, not a document count: the Library subtitle uses it to say
    whether the pipeline directories are on the API host at all. An empty Docker
    placeholder directory does not count, which is the case it exists to reject.
    """
    if not path or not path.is_dir():
        return False
    output = path / "output"
    if not output.is_dir():
        return False
    return any(output.glob("*.json"))


def selected(only: Optional[Iterable[str]] = None) -> Iterator[Corpus]:
    """The corpora to sync. ``None`` means all of them; unknown labels raise.

    Raising beats ignoring: ``--rules-only`` misspelt should not silently sync
    everything, which is the expensive direction of that mistake.
    """
    if only is None:
        yield from CORPORA
        return
    wanted = list(only)
    unknown = sorted(set(wanted) - set(LABELS))
    if unknown:
        raise ValueError(
            f"unknown corpus {', '.join(unknown)} (known: {', '.join(LABELS)})"
        )
    for corpus in CORPORA:  # registry order, not caller order
        if corpus.label in wanted:
            yield corpus


def _demo() -> None:
    assert LABELS == ("ordinance", "acts", "rules")
    assert [c.label for c in selected()] == list(LABELS)
    # registry order is preserved regardless of how the caller lists them
    assert [c.label for c in selected(["rules", "ordinance"])] == ["ordinance", "rules"]
    assert [c.label for c in selected([])] == []
    try:
        list(selected(["acts", "nope"]))
    except ValueError as err:
        assert "nope" in str(err) and "known:" in str(err), err
    else:  # pragma: no cover
        raise AssertionError("an unknown corpus must raise, not be ignored")
    os.environ["CORPUS_RULES"] = "/tmp/rules-elsewhere"
    assert get("rules").path() == Path("/tmp/rules-elsewhere")
    del os.environ["CORPUS_RULES"]
    assert get("rules").path() == REPO_ROOT / "data" / "corpora" / "rules"
    assert not corpus_root_configured(None)
    assert not corpus_root_configured(Path("/nonexistent-corpus"))
    print("corpus_registry self-check passed")


if __name__ == "__main__":
    _demo()

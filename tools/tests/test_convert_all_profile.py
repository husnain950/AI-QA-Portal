"""``--profile`` reaches the child, and never reaches a lane that cannot take it.

Both halves are about the same hazard.  ``convert_all`` is the only practical way
to convert 168 PDFs, so a flag it silently drops means a whole re-conversion runs
under the wrong profile and nothing says so.  And the ordinance lane routes to
``fbr_ingest``, whose ``run`` takes no profile: without the up-front guard,
``convert.py`` exits 2 on each of its 45 files, which is not an
``_is_env_failure``, so ``_quarantine`` moves every existing ordinance JSON out of
the corpus.  A flag typo must not be able to empty a lane.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import convert_all  # noqa: E402


def _argv_for(profile: str, monkeypatch, tmp_path) -> list[str]:
    """Run one ``convert`` with the child stubbed out, and return its argv."""
    seen: list[list[str]] = []

    class _Done:
        returncode = 0
        stdout = stderr = ""

    monkeypatch.setattr(convert_all.subprocess, "run",
                        lambda argv, **kw: seen.append(argv) or _Done())
    monkeypatch.setattr(convert_all, "OUT", tmp_path)
    convert_all.convert(tmp_path / "x.pdf", keep_log=False, profile=profile)
    return seen[0]


def test_profile_reaches_the_child(monkeypatch, tmp_path):
    assert "--profile" not in _argv_for("lane", monkeypatch, tmp_path)
    argv = _argv_for("auto", monkeypatch, tmp_path)
    assert argv[argv.index("--profile") + 1] == "auto"


def test_a_lane_with_no_profile_is_refused_before_anything_converts(
        monkeypatch, capsys, tmp_path):
    """fbr_ingest takes no profile, so the run must stop before it converts.

    The source directory is faked present: without that this passes on CI for
    the wrong reason -- the corpus is gitignored, so the earlier "no source
    directory" check would return 2 whether or not the guard exists.
    """
    converted = []
    monkeypatch.setattr(convert_all, "convert",
                        lambda *a, **k: converted.append(a) or {})
    monkeypatch.setattr(convert_all.pathlib.Path, "is_dir", lambda self: True)
    assert convert_all.main(["ordinance", "--profile", "auto"]) == 2
    assert "takes no profile" in capsys.readouterr().err
    assert not converted

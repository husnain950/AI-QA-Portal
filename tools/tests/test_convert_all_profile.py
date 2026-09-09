"""``--profile`` reaches the child and route guards run before conversion.

``convert_all`` is the only practical way to convert a full corpus, so a flag it
silently drops means a whole re-conversion runs under the wrong profile.  This is
especially important now that the child defaults to auto: explicit ``lane`` must
be forwarded too.  Route validation still happens up front, before a bad parser
binding can make every child quarantine its previous output.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import convert  # noqa: E402
import convert_all  # noqa: E402


def test_single_converter_defaults_to_auto_and_keeps_lane_override():
    parser = convert.build_parser()
    assert parser.parse_args(["acts", "x.pdf"]).profile == "auto"
    assert parser.parse_args(["acts", "x.pdf", "--profile", "lane"]).profile == "lane"


def _argv_for(profile: str | None, monkeypatch, tmp_path) -> list[str]:
    """Run one ``convert`` with the child stubbed out, and return its argv."""
    seen: list[list[str]] = []

    class _Done:
        returncode = 0
        stdout = stderr = ""

    monkeypatch.setattr(convert_all.subprocess, "run",
                        lambda argv, **kw: seen.append(argv) or _Done())
    monkeypatch.setattr(convert_all, "OUT", tmp_path)
    kwargs = {} if profile is None else {"profile": profile}
    convert_all.convert(tmp_path / "x.pdf", keep_log=False, **kwargs)
    return seen[0]


def test_profile_reaches_the_child(monkeypatch, tmp_path):
    for requested, expected in ((None, "auto"), ("auto", "auto"), ("lane", "lane")):
        argv = _argv_for(requested, monkeypatch, tmp_path)
        assert argv[argv.index("--profile") + 1] == expected


def test_auto_routes_are_validated_before_anything_converts(monkeypatch, tmp_path):
    seen = []

    class _Route:
        def load(self):
            seen.append("loaded")

    class _Corpus:
        def parser_for(self, pdf, *, profile):
            seen.append((pdf, profile))
            return _Route()

    monkeypatch.setattr(convert_all, "get", lambda lane: _Corpus())
    monkeypatch.setattr(convert_all, "LANE", "ordinance")
    pdfs = [tmp_path / "ict.pdf", tmp_path / "income-tax.pdf"]
    assert convert_all._validate_routes(pdfs, "auto")
    assert seen == [
        (pdfs[0], "auto"),
        "loaded",
        (pdfs[1], "auto"),
        "loaded",
    ]


def test_an_invalid_route_stops_the_batch_guard(monkeypatch, capsys, tmp_path):
    class _Route:
        def load(self):
            raise ValueError("auto is unsupported")

    class _Corpus:
        def parser_for(self, pdf, *, profile):
            return _Route()

    monkeypatch.setattr(convert_all, "get", lambda lane: _Corpus())
    assert not convert_all._validate_routes([tmp_path / "x.pdf"], "auto")
    assert "invalid parser route" in capsys.readouterr().err

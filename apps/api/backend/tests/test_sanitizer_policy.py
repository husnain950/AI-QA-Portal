"""One allowlist, enforced twice.

The browser sanitizes stored HTML again because stored HTML is a trust boundary.
What it must not do is disagree: `sanitizeHtml.js` carried its own, narrower
allowlist and quietly deleted what `html_sanitizer.py` had carefully kept -- seven
classes with live stylesheet rules (11,349 occurrences across the two corpora) and
the `flex: 0 0 N%` footnote-table widths this module has a narrow, audited exception
for. The second line of defence was undoing the first.

The policy is now generated from the Python module and committed; this fails when the
committed file drifts, the same way `tools/suite/register.json` is gated.
"""

import json
import pathlib

from backend.services import html_sanitizer

_POLICY = pathlib.Path(__file__).resolve().parents[4].joinpath(
    *html_sanitizer._POLICY_PATH
)


def test_the_committed_policy_matches_the_module():
    assert _POLICY.is_file(), f"{_POLICY} is missing"
    committed = json.loads(_POLICY.read_text(encoding="utf-8"))
    assert committed == html_sanitizer.policy(), (
        "apps/web/src/utils/sanitizerPolicy.json is stale. Regenerate it with\n"
        "  python -m backend.services.html_sanitizer --write"
    )


def test_the_policy_carries_the_classes_the_client_used_to_drop():
    """Named individually, because each one is a construct that renders as
    undifferentiated prose without it."""
    known = set(html_sanitizer.policy()["knownClasses"])
    assert {
        "fn-table", "omitted-bracket", "explanation", "defn", "formula", "frac",
        "legend",
    } <= known


def test_the_gazette_block_kinds_survive():
    """`fbr_ingest.builder.GAZETTE_KINDS`, all five, all with stylesheet rules.

    They were dropped here -- 965 occurrences across the corpus -- and nothing
    noticed, because the one pane that renders them injected stored HTML without
    sanitizing and so never saw the loss. Bound to the pipeline's own tuple so a
    sixth kind cannot be added there and silently discarded here.
    """
    from fbr_ingest.builder import GAZETTE_KINDS

    known = set(html_sanitizer.policy()["knownClasses"])
    assert set(GAZETTE_KINDS) <= known, set(GAZETTE_KINDS) - known


def test_the_policy_never_advertises_a_dangerous_tag():
    p = html_sanitizer.policy()
    assert not set(p["allowedTags"]) & set(p["forbidTags"])
    for tag in ("script", "style", "iframe", "object", "embed"):
        assert tag in p["forbidTags"], tag


def test_the_flex_pattern_is_exactly_the_one_the_module_applies():
    """The client applies this pattern verbatim, so a widening here widens both."""
    import re

    pattern = re.compile(html_sanitizer.policy()["flexBasisPattern"])
    assert pattern.match("0 0 42%")
    assert pattern.match("0 0 12.5%")
    assert not pattern.match("1 0 42%")
    assert not pattern.match("0 0 42% ; position: fixed")
    assert not pattern.match("0 0 42px")


def test_the_narrow_exception_survives_a_real_footnote_table():
    kept = html_sanitizer.sanitize_html(
        '<div class="fn-table"><div class="fn-cell" style="flex: 0 0 33.3333%">Rate</div></div>'
    )
    assert "flex:0 0 33.3333%" in kept.html
    assert "fn-table" in kept.html


def test_everything_else_in_a_style_attribute_is_still_dropped():
    out = html_sanitizer.sanitize_html(
        '<div style="position:fixed;top:0;background:url(javascript:alert(1))">x</div>'
    )
    assert "position" not in out.html
    assert "javascript" not in out.html

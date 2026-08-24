"""How this codebase compares legal text and markup across editions.

Both functions existed twice, byte for byte, in `variants` and `detectors` -- the two
modules that decide whether two editions of a section say the same thing. They have to
agree: `variants` mints the key a reviewer approves, and `detectors` decides whether to
raise a finding about it. Two copies of the rule is two chances for that to drift.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

#: The block-level tags whose ORDER defines a leaf's shape. Inline markup is
#: deliberately absent: a bolded word is a text difference, not a structural one.
_BLOCK_TAGS = (
    r"p|div|table|tr|td|th|ul|ol|li|h[1-6]|blockquote|pre|section|article|aside"
    r"|nav|header|footer|figure|figcaption|details|summary|dl|dt|dd"
)
_BLOCK_TAG_RE = re.compile(rf"<(/?(?:{_BLOCK_TAGS}))\b", re.IGNORECASE)


def norm_text(text: str) -> str:
    """NFKC + whitespace collapse, no casefolding.

    Case is preserved because these documents use it structurally -- an all-caps
    heading and its sentence-case cross-reference are not the same string.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def html_shape(html: str) -> str:
    """SHA256 of the ordered block-tag sequence.

    A fingerprint of structure alone, so a re-parse that rewrites wording is not
    reported as a structural change, and one that turns a paragraph into a table is.
    """
    tags = _BLOCK_TAG_RE.findall(html or "")
    return hashlib.sha256("|".join(t.lower() for t in tags).encode()).hexdigest()


def _demo() -> None:
    assert norm_text("  a  b\n\tc ") == "a b c"
    assert norm_text("Ａ Ｂ") == "A B"           # NFKC folds fullwidth forms
    assert norm_text("ACT") != norm_text("act")  # case is structural, never folded
    # same structure, different words -> same shape
    assert html_shape("<p>one</p><ul><li>a</li></ul>") == \
           html_shape("<p>two</p><ul><li>b</li></ul>")
    # inline markup is not structure
    assert html_shape("<p>a <strong>b</strong></p>") == html_shape("<p>ab</p>")
    # a paragraph becoming a table IS structure
    assert html_shape("<p>a</p>") != html_shape("<table><tr><td>a</td></tr></table>")
    assert html_shape("") == html_shape(None)
    print("textnorm self-check passed")


if __name__ == "__main__":
    _demo()

"""Carry a reviewer's highlight across a re-parse of the leaf it sits in.

An annotation stores ``(highlighted_text, start_offset, end_offset)`` measured against
the *rendered* container's ``textContent`` -- see
``frontend/src/hooks/useTextSelection.js``, which walks the DOM after
``container.innerHTML = html_content``. So the string the offsets index into is exactly
"``html_content`` with its tags removed and its entities decoded", which
:func:`container_text` reproduces here. The ``<mark>`` and footnote decoration the panel
adds afterwards inserts no text nodes, so it does not shift anything.

Re-anchoring is deliberately conservative: it moves an annotation only when it can
identify the *same* text unambiguously. Anything else is reported as ``needs_recheck``
for a human, because silently re-pointing a finding at the wrong clause of a tax statute
is worse than asking someone to look again.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional

# Stored either side of a highlight so a repeated phrase can still be told apart.
CONTEXT_CHARS = 60

ANCHORED = "anchored"
NEEDS_RECHECK = "needs_recheck"
ORPHANED = "orphaned"


class _TextExtractor(HTMLParser):
    """Concatenates text nodes the way the DOM's ``textContent`` does."""

    def __init__(self) -> None:
        # convert_charrefs=True decodes &amp; / &#8212; into handle_data for us,
        # matching what the browser puts in the text node.
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def error(self, message: str) -> None:  # pragma: no cover - py3.12 never calls it
        pass


def container_text(html: Optional[str]) -> str:
    """The string an annotation's offsets are measured against."""
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts)


def capture_context(text: str, start: int, end: int) -> tuple[str, str]:
    """Context either side of a highlight, for annotations created server-side."""
    return text[max(0, start - CONTEXT_CHARS):start], text[end:end + CONTEXT_CHARS]


@dataclass(frozen=True)
class Anchor:
    start: int
    end: int
    status: str
    reason: str = ""

    @property
    def moved(self) -> bool:
        return self.status == ANCHORED


def _common_prefix(a: str, b: str) -> int:
    limit = min(len(a), len(b))
    i = 0
    while i < limit and a[i] == b[i]:
        i += 1
    return i


def _all_occurrences(haystack: str, needle: str) -> List[int]:
    found, index = [], haystack.find(needle)
    while index != -1:
        found.append(index)
        index = haystack.find(needle, index + 1)
    return found


def reanchor(
    new_text: str,
    *,
    highlighted_text: str,
    start_offset: int,
    end_offset: int,
    context_before: Optional[str] = None,
    context_after: Optional[str] = None,
) -> Anchor:
    """Locate ``highlighted_text`` in ``new_text`` and return where it now sits.

    Order: the old offsets if they still hold; a unique exact match; a repeated match
    disambiguated by stored context. Everything else keeps the old offsets and is
    flagged ``needs_recheck``.
    """
    if not highlighted_text:
        return Anchor(start_offset, end_offset, NEEDS_RECHECK, "annotation has no text")

    if new_text[start_offset:end_offset] == highlighted_text:
        return Anchor(start_offset, end_offset, ANCHORED, "offsets unchanged")

    matches = _all_occurrences(new_text, highlighted_text)
    if not matches:
        return Anchor(start_offset, end_offset, NEEDS_RECHECK, "text no longer present")

    if len(matches) == 1:
        start = matches[0]
        return Anchor(start, start + len(highlighted_text), ANCHORED, "unique match")

    if not (context_before or context_after):
        return Anchor(
            start_offset,
            end_offset,
            NEEDS_RECHECK,
            f"{len(matches)} identical matches and no stored context",
        )

    # Score each candidate by how much of the recorded surroundings it reproduces.
    # `context_before` is compared right-to-left because it is the text leading *into*
    # the highlight; the characters nearest the highlight are the telling ones.
    before = context_before or ""
    after = context_after or ""
    scored = []
    for start in matches:
        end = start + len(highlighted_text)
        score = _common_prefix(before[::-1], new_text[:start][::-1])
        score += _common_prefix(after, new_text[end:])
        scored.append((score, start))
    scored.sort(reverse=True)

    best_score, best_start = scored[0]
    if best_score == 0 or best_score == scored[1][0]:
        return Anchor(
            start_offset,
            end_offset,
            NEEDS_RECHECK,
            f"{len(matches)} identical matches, context did not separate them",
        )
    return Anchor(
        best_start,
        best_start + len(highlighted_text),
        ANCHORED,
        "match resolved by surrounding context",
    )


def demo() -> None:
    """Self-check against the markup the pipeline actually emits."""
    html = (
        '<h4 class="section-heading">1. Short title and commencement.&#8212;</h4>\n'
        '<ol class="subsection" style="list-style-type: none;">\n'
        "<li>(1) This Act shall be called the Tax Laws &amp; (Amendment) Act, 2023.</li>\n"
        "<li>(2) It shall come into force at once.</li>\n</ol>"
    )
    text = container_text(html)
    assert "—" in text, "entities must be decoded like the DOM does"
    assert "&amp;" not in text and " & " in text
    assert "<li>" not in text and "class=" not in text, text
    # textContent keeps the whitespace between elements; it does not collapse it.
    assert "\n" in text

    body = "alpha bravo charlie delta"
    start, end = body.index("charlie"), body.index("charlie") + len("charlie")

    # 1. offsets still valid -> untouched
    a = reanchor(body, highlighted_text="charlie", start_offset=start, end_offset=end)
    assert a.status == ANCHORED and (a.start, a.end) == (start, end), a

    # 2. text moved, single occurrence -> follows it
    moved = "prefix inserted " + body
    a = reanchor(moved, highlighted_text="charlie", start_offset=start, end_offset=end)
    assert a.status == ANCHORED and moved[a.start:a.end] == "charlie", a

    # 3. text gone -> needs_recheck, offsets preserved for the record
    a = reanchor("nothing alike", highlighted_text="charlie",
                 start_offset=start, end_offset=end)
    assert a.status == NEEDS_RECHECK and (a.start, a.end) == (start, end), a

    # 4. repeated text and the old offsets no longer hold -> refuses to guess
    twice = "zz charlie and charlie"
    a = reanchor(twice, highlighted_text="charlie", start_offset=0, end_offset=7)
    assert a.status == NEEDS_RECHECK and (a.start, a.end) == (0, 7), a

    # 5. same, but stored context separates them -> picks the right one
    a = reanchor(
        twice,
        highlighted_text="charlie",
        start_offset=0,
        end_offset=7,
        context_before="and ",
        context_after="",
    )
    assert a.status == ANCHORED and a.start == twice.rindex("charlie"), a

    # 5b. still-valid offsets win over everything, even when the text repeats
    a = reanchor("charlie and charlie", highlighted_text="charlie",
                 start_offset=0, end_offset=7)
    assert a.status == ANCHORED and a.start == 0, a

    # 6. context that fits both equally -> still refuses
    a = reanchor(
        "x charlie y x charlie y",
        highlighted_text="charlie",
        start_offset=0,
        end_offset=7,
        context_before="x ",
        context_after=" y",
    )
    assert a.status == NEEDS_RECHECK, a

    # 7. capture_context round-trips
    b, aft = capture_context(body, start, end)
    assert body[start - len(b):start] == b and body[end:end + len(aft)] == aft
    print("anchoring: ok")


if __name__ == "__main__":
    demo()

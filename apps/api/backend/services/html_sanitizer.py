"""Fidelity-oriented legal HTML sanitizer used before persistence and rendering."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser

SANITIZER_VERSION = "legal-html-v1"

ALLOWED_TAGS = frozenset(
    {
        "article", "b", "blockquote", "br", "caption", "code", "col", "colgroup",
        "dd", "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2", "h3",
        "h4", "h5", "h6", "hr", "i", "li", "ol", "p", "pre", "s", "section",
        "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th",
        "thead", "tr", "u", "ul",
    }
)
DANGEROUS_TAGS = frozenset(
    {"script", "style", "svg", "math", "iframe", "object", "embed", "audio", "video", "img", "source"}
)
DANGEROUS_CONTAINERS = DANGEROUS_TAGS - {"img", "source", "embed"}
VOID_TAGS = frozenset({"br", "hr", "col"})
GLOBAL_ATTRS = frozenset({"class", "title", "lang", "dir"})
TAG_ATTRS = {
    "td": frozenset({"colspan", "rowspan", "headers"}),
    "th": frozenset({"colspan", "rowspan", "headers", "scope", "abbr"}),
    "ol": frozenset({"start", "reversed", "type"}),
    "li": frozenset({"value"}),
    "sup": frozenset({"data-ref"}),
    "col": frozenset({"span"}),
    "colgroup": frozenset({"span"}),
}
KNOWN_CLASSES = frozenset(
    {
        "section-heading", "schedule-heading", "subsection", "paragraph", "subparagraph",
        "clause", "subclause", "cite", "citation", "footnote", "footnote-marker",
        "marker", "proviso", "fbr-table", "table", "table-responsive",
        # Emitted by the ingest pipelines; each already has a stylesheet rule (see
        # styles/08-html-panel-styles.css and styles/10-footnotes-panel.css). Without
        # them the class is dropped and the construct renders as undifferentiated
        # prose -- measured at 11,349 occurrences across the two corpora.
        "fn-table", "omitted-bracket", "explanation", "defn", "formula", "frac",
        "legend",
        # The gazette block kinds -- `fbr_ingest.builder.GAZETTE_KINDS`, which names
        # exactly these five and nothing else. Each has a rule in
        # styles/08-html-panel-styles.css, and each was being dropped here: measured
        # at 965 occurrences across the corpus (act-title 589, recital 203,
        # act-long-title 111, enacting-formula 60, enacting-clause 2). Nothing
        # noticed, because the one pane that renders them injected stored HTML
        # without sanitizing and so never saw the loss.
        "act-title", "act-long-title", "recital", "enacting-formula",
        "enacting-clause",
        "crx-align-center", "crx-align-right",
        "crx-align-justify", "crx-bold", "crx-italic", "crx-underline",
        "crx-list-unstyled", "crx-pad-zero", "crx-indent-1", "crx-indent-2",
        "crx-indent-3", "crx-indent-4", "crx-super", "crx-sub",
    }
)


@dataclass(frozen=True)
class SanitizedHtml:
    html: str
    changed: bool
    diagnostics: tuple[str, ...]
    text_fidelity: bool
    structure_fidelity: bool


#: ``flex: 0 0 <pct>%`` -- a footnote rate-table column width. This one declaration is
#: data, not decoration: the width is measured from the PDF's own column geometry, it
#: differs per table, and no class can carry a continuous percentage. Dropping it
#: collapses every fn-table grid into stacked divs while ``text_fidelity`` and
#: ``structure_fidelity`` both still report True, because neither looks at layout.
#:
#: The pattern is deliberately exact -- two literal zeros and a bounded percentage --
#: so nothing else in a ``style`` attribute can reach the output through it.
_FLEX_BASIS_RE = re.compile(r"^0\s+0\s+(\d{1,3}(?:\.\d{1,4})?)%$")


def _flex_basis(value: str) -> str | None:
    """The safe re-emittable ``flex`` value in ``value``, or None."""
    for declaration in value.split(";"):
        prop, _, raw = declaration.partition(":")
        if prop.strip().lower() != "flex":
            continue
        match = _FLEX_BASIS_RE.match(raw.strip().lower())
        if match and 0.0 < float(match.group(1)) <= 100.0:
            return f"0 0 {match.group(1)}%"
    return None


def _style_classes(value: str) -> set[str]:
    classes: set[str] = set()
    for declaration in value.split(";"):
        if ":" not in declaration:
            continue
        prop, raw = (part.strip().lower() for part in declaration.split(":", 1))
        if prop == "text-align" and raw in {"center", "right", "justify"}:
            classes.add(f"crx-align-{raw}")
        elif prop == "font-weight" and raw in {"bold", "600", "700", "800", "900"}:
            classes.add("crx-bold")
        elif prop == "font-style" and raw == "italic":
            classes.add("crx-italic")
        elif prop == "text-decoration" and "underline" in raw:
            classes.add("crx-underline")
        elif prop == "list-style-type" and raw == "none":
            classes.add("crx-list-unstyled")
        elif prop == "padding-left" and raw in {"0", "0px", "0em", "0rem"}:
            classes.add("crx-pad-zero")
        elif prop == "margin-left":
            match = re.fullmatch(r"([0-9.]+)(em|rem|px|pt)", raw)
            if match:
                amount = float(match.group(1))
                unit = match.group(2)
                em = amount / 16 if unit == "px" else amount / 12 if unit == "pt" else amount
                classes.add(f"crx-indent-{min(4, max(1, round(em)))}")
        elif prop == "vertical-align" and raw in {"super", "sub"}:
            classes.add("crx-super" if raw == "super" else "crx-sub")
    return classes


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.drop = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in DANGEROUS_CONTAINERS:
            self.drop += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in DANGEROUS_CONTAINERS and self.drop:
            self.drop -= 1

    def handle_data(self, data: str) -> None:
        if not self.drop:
            self.parts.append(data)


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.diagnostics: list[str] = []
        self.drop = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in DANGEROUS_TAGS:
            if tag in DANGEROUS_CONTAINERS:
                self.drop += 1
            self.diagnostics.append(f"dropped_tag:{tag}")
            return
        if self.drop:
            return
        if tag not in ALLOWED_TAGS:
            self.diagnostics.append(f"unwrapped_tag:{tag}")
            return
        classes: set[str] = set()
        clean: list[tuple[str, str | None]] = []
        # Attributes keep their source order, and the merged class list stays in the slot
        # the original class attribute held. Untouched markup then round-trips
        # byte-identically, which is what makes `changed` worth storing.
        class_slot: int | None = None
        for name, value in attrs:
            name = name.lower()
            value = value or ""
            if name.startswith("on") or name in {"href", "src", "srcset"}:
                self.diagnostics.append(f"dropped_attr:{tag}.{name}")
                continue
            if name == "style":
                classes.update(_style_classes(value))
                basis = _flex_basis(value)
                if basis is not None:
                    clean.append(("style", f"flex:{basis}"))
                self.diagnostics.append(f"converted_style:{tag}")
                continue
            if name == "class":
                observed = set(value.split())
                classes.update(observed & KNOWN_CLASSES)
                if observed - KNOWN_CLASSES:
                    self.diagnostics.append(f"dropped_class:{tag}")
                if class_slot is None:
                    class_slot = len(clean)
                    clean.append(("class", ""))
                continue
            if name in GLOBAL_ATTRS or name in TAG_ATTRS.get(tag, ()):
                clean.append((name, value))
            else:
                self.diagnostics.append(f"dropped_attr:{tag}.{name}")
        if classes:
            rendered_classes = " ".join(sorted(classes))
            if class_slot is None:
                clean.append(("class", rendered_classes))
            else:
                clean[class_slot] = ("class", rendered_classes)
        elif class_slot is not None:
            del clean[class_slot]
        rendered = "".join(
            f" {name}" if value is None else f' {name}="{html.escape(value, quote=True)}"'
            for name, value in clean
        )
        self.out.append(f"<{tag}{rendered}>")

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in DANGEROUS_CONTAINERS:
            if self.drop:
                self.drop -= 1
            return
        if not self.drop and tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.drop:
            self.out.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self.drop:
            self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.drop:
            self.out.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.diagnostics.append("dropped_comment")


class _Structure(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, tuple[tuple[str, str], ...]]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag not in {"table", "thead", "tbody", "tfoot", "tr", "td", "th", "ol", "ul", "li", "sup"}:
            return
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        relevant = tuple(
            sorted(
                (name, attrs_dict[name])
                for name in ("colspan", "rowspan", "start", "value", "type")
                if name in attrs_dict
            )
        )
        self.items.append((tag, relevant))


def structure_signature(value: str) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    parser = _Structure()
    parser.feed(value or "")
    parser.close()
    return tuple(parser.items)


def visible_text(value: str) -> str:
    parser = _Text()
    parser.feed(value or "")
    parser.close()
    return "".join(parser.parts)


def sanitize_html(value: str) -> SanitizedHtml:
    source = value or ""
    parser = _Sanitizer()
    parser.feed(source)
    parser.close()
    cleaned = "".join(parser.out)
    return SanitizedHtml(
        html=cleaned,
        changed=cleaned != source,
        diagnostics=tuple(dict.fromkeys(parser.diagnostics)),
        text_fidelity=visible_text(source) == visible_text(cleaned),
        structure_fidelity=structure_signature(source) == structure_signature(cleaned),
    )


# --- one policy, two enforcers ------------------------------------------------
#
# The stored HTML is sanitized here, at ingest. The browser sanitizes it again --
# stored HTML is a trust boundary and defence in depth is worth having -- but it was
# doing so against a SEPARATE, NARROWER allowlist maintained by hand in
# `apps/web/src/utils/sanitizeHtml.js`, and the two had drifted:
#
#   * the client dropped `fn-table`, `omitted-bracket`, `explanation`, `defn`,
#     `formula`, `frac` and `legend` -- 11,349 occurrences across the two corpora,
#     every one with a live stylesheet rule;
#   * and it dropped the `flex: 0 0 N%` widths this module was written to preserve,
#     in `FootnotePanel`, the only place `.fn-table` renders.
#
# So the second line of defence was quietly deleting what the first had carefully
# kept. Now one policy is exported and the client imports it, in the same shape the
# anomaly register uses: a committed artifact with a test that fails when it drifts.

_POLICY_PATH = ("apps", "web", "src", "utils", "sanitizerPolicy.json")


def policy() -> dict:
    """The allowlist, as data, for any enforcer that is not this module."""
    return {
        "version": SANITIZER_VERSION,
        "allowedTags": sorted(ALLOWED_TAGS),
        "forbidTags": sorted(DANGEROUS_TAGS),
        "allowedAttrs": sorted(
            GLOBAL_ATTRS.union(*TAG_ATTRS.values()) if TAG_ATTRS else GLOBAL_ATTRS
        ),
        "knownClasses": sorted(KNOWN_CLASSES),
        # The one style declaration that survives, as a pattern the client can apply
        # verbatim. Keeping it here means the exactness argument above is made once.
        "flexBasisPattern": _FLEX_BASIS_RE.pattern,
    }


def _policy_json() -> str:
    import json

    return json.dumps(policy(), indent=2, sort_keys=True) + "\n"


def _demo() -> None:
    """Self-check: the policy is complete and the exception still round-trips."""
    p = policy()
    assert p["version"] == SANITIZER_VERSION
    for name in ("fn-table", "omitted-bracket", "explanation", "defn", "formula",
                 "frac", "legend"):
        assert name in p["knownClasses"], name
    assert "script" in p["forbidTags"] and "script" not in p["allowedTags"]
    assert "data-ref" in p["allowedAttrs"], "cite -> footnote linkage travels on it"

    # The narrow exception, both directions.
    kept = sanitize_html('<div class="fn-table"><div style="flex: 0 0 42%">x</div></div>')
    # Re-emitted canonically, without the space after the colon.
    assert "flex:0 0 42%" in kept.html, kept.html
    assert "fn-table" in kept.html
    dropped = sanitize_html('<div style="position: fixed; top: 0">x</div>')
    assert "position" not in dropped.html, dropped.html
    print("html_sanitizer: ok")


if __name__ == "__main__":
    import pathlib
    import sys

    root = pathlib.Path(__file__).resolve().parents[4]
    target = root.joinpath(*_POLICY_PATH)
    if "--write" in sys.argv:
        target.write_text(_policy_json(), encoding="utf-8")
        print(f"wrote {target}")
    else:
        _demo()

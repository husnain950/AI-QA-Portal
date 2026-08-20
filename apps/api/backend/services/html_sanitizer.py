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
        "marker", "proviso", "fbr-table", "table", "table-responsive", "crx-align-center", "crx-align-right",
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

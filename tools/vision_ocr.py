"""Offline vision-model transcription of scanned pages, voted into a sidecar.

The conversion path never calls a model (README: no LLM/vision in conversion).
This tool runs OUTSIDE it: each scanned page is sent to several vision models,
their transcriptions are voted token by token, and the result is frozen into
``<pdf>.vision.json`` next to the PDF.  ``legal_ingest.ocr.ocr_page`` then
reads that sidecar deterministically, with no network access.

    tools/vision_ocr.py transcribe <pdf> [--pages 3,5] [--models a,b,c]
    tools/vision_ocr.py vote <pdf> [--pages 3,5] [--models a,b,c]

Raw responses are cached as ``<pdf>.vision/p<N>.<model>.txt``, so re-running
costs nothing.  Rulings made against the page image -- splits resolved, a page
proofread -- live in ``<pdf>.vision.rulings.json`` and survive a re-vote.  A
``p<N>.claude-code.txt`` is a human transcription standing in for a reader that
gave up on the page.  Needs OPENPATHS_API_KEY and OPENPATHS_BASE_URL.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))

_RENDER_LOCK = threading.Lock()
#: who rules on splits against the page image (recorded in the sidecar)
ADJUDICATOR = "claude-opus-5-5 via Claude Code, image-checked"
HUMAN = "claude-code"         # raw file p<N>.claude-code.txt
DEFAULT_MODELS = ["claude-sonnet-5", "claude-opus-5-5", "gemini-2.5-pro"]
PROMPT = """You are transcribing one scanned page of a Pakistani statute for a legal corpus.
Transcribe EXACTLY what is printed, in reading order, one output line per printed line.
- Do not correct spelling, grammar, numbering or punctuation; do not modernise or complete anything.
- Keep every enumerator, rule/section number, date, amount, SRO reference and footnote marker exactly.
- Tables: one table row per line, cells separated by " | ".
- Text you cannot read: write [?] in its place. Never guess.
- Handwriting, stamps and signatures: write [handwritten] / [stamp] / [signature].
Output only the transcription: no commentary, no markdown fences."""


def raw_dir(pdf: str) -> Path:
    return Path(pdf + ".vision")


def sidecar_path(pdf: str) -> Path:
    return Path(pdf + ".vision.json")


def _slug(model: str) -> str:
    return model.replace("/", "_")


def raw_path(pdf: str, page: int, model: str) -> Path:
    return raw_dir(pdf) / f"p{page}.{_slug(model)}.txt"


def transcribe_one(pdf: str, page: int, model: str) -> str:
    from legal_ingest.ocr import render_png

    out = raw_path(pdf, page, model)
    if out.exists():
        return out.read_text()
    with _RENDER_LOCK:                  # pdfium is not thread-safe
        png = render_png(pdf, page, 200)   # legible, and under every model's limit
    text = _ask(model, png)
    out.parent.mkdir(exist_ok=True)
    out.write_text(text)
    return text


def _ask(model: str, png_bytes: bytes) -> str:
    import urllib.error
    import urllib.request

    png = base64.b64encode(png_bytes).decode()
    body = {"model": model, "temperature": 0, "max_tokens": 16000,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{png}"}}]}]}
    base = os.environ["OPENPATHS_BASE_URL"].rstrip("/")
    req = urllib.request.Request(
        f"{base}/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {os.environ['OPENPATHS_API_KEY']}",
                 "Content-Type": "application/json",
                 "User-Agent": "crx-vision-ocr/1"})   # Cloudflare 1010s urllib's
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                resp = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 2:
                raise RuntimeError(f"{e.code} {e.read()[:300]!r}") from e
        except urllib.error.URLError:
            if attempt == 2:
                raise
    choice = resp["choices"][0]
    if choice.get("finish_reason") not in ("stop", None):
        # a truncated page must never be voted as if it were the whole page
        raise RuntimeError(f"finish_reason={choice.get('finish_reason')}")
    text = (choice["message"]["content"] or "").strip()
    if not text:
        raise RuntimeError("empty transcription")
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    return text


def body_scanned_pages(pdf: str) -> list[int]:
    """Every page ``pipeline.run`` could OCR -- the TOC is included on purpose,
    so a change in where the body is detected to start needs no re-run."""
    from legal_ingest.ocr import scanned_pages
    return scanned_pages(pdf)[1]


def _norm(t: str) -> str:
    return t.strip()                    # verbatim: case is part of the text


def vote_line_tokens(readings: list[list[str]],
                     rejected: list | None = None) -> list[dict]:
    """Majority-vote three token sequences, aligned onto the first.

    Each output token is ``{"text", "votes", "alts"}``.  ``votes`` is how many
    readings carried the accepted text; a 1-vote token is a three-way split
    and must be reviewed.  A token only ONE reading carries is outvoted: it is
    left out and appended to ``rejected`` so the page can be audited.
    """
    rejected = [] if rejected is None else rejected
    anchor, others = readings[0], readings[1:]
    slots: list[list[str | None]] = [[t] for t in anchor]
    gaps: dict[int, list[list[str]]] = {}      # insertion before anchor index
    for o in others:
        sm = SequenceMatcher(None, [_norm(t) for t in anchor],
                             [_norm(t) for t in o], autojunk=False)
        seen = [False] * len(anchor)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ("equal", "replace") and i2 - i1 == j2 - j1:
                for k in range(i2 - i1):
                    slots[i1 + k].append(o[j1 + k])
                    seen[i1 + k] = True
            elif tag == "replace":
                # unequal split ("1 (a)" vs "1(a)"): join both sides to compare
                slots[i1].append(" ".join(o[j1:j2]))
                seen[i1] = True
                for k in range(i1 + 1, i2):
                    slots[k].append("")
                    seen[k] = True
            elif tag == "insert":
                gaps.setdefault(i1, []).append(o[j1:j2])
        for k, s in enumerate(seen):
            if not s:
                slots[k].append(None)           # this reading dropped it
    out: list[dict] = []

    def emit_gap(i):
        ins = gaps.get(i, [])
        if len(ins) >= 2 and [_norm(t) for t in ins[0]] == [_norm(t) for t in ins[1]]:
            for t in ins[0]:
                out.append({"text": t, "votes": 2, "alts": [None], "a": max(i - 1, 0)})
        else:
            rejected.extend((len(out), t) for t in ins)

    for i, slot in enumerate(slots):
        emit_gap(i)
        own = slot[0]
        # a joined replace is compared against the anchor run it replaced
        cand = [s for s in slot if s is not None]
        tally: dict[str, int] = {}
        for s in cand:
            tally[_norm(s)] = tally.get(_norm(s), 0) + 1
        best = max(tally, key=lambda k: (tally[k], k == _norm(own)))
        text = own if best == _norm(own) else next(s for s in cand if _norm(s) == best)
        dropped = slot.count(None)
        if dropped >= 2:
            # two of three readings do not have this token at all
            rejected.append((len(out), [own]))
            continue
        if text:
            out.append({"text": text, "votes": tally[best], "a": i,
                        "alts": [s for s in slot if s is not None and _norm(s) != best]})
    emit_gap(len(slots))
    return [t for t in out if t["text"]]


#: layout the models draw differently and the pipeline never prints: table
#: pipes, checkbox glyphs, fill-in rules
_LAYOUT = re.compile(r"^(\||[☐□■✓✔♦•]+|_+|\.{3,}|[\[\]\-]+)$")


#: the prompt's own notes for what is not print ("[handwritten: 78]",
#: "[stamp]"): the corpus carries printed text only
_META = re.compile(r"\[(?:handwritten|stamp|signature|emblem|logo|seal)[^\]]*\]", re.I)


def tokens_of(text: str) -> list[str]:
    text = _META.sub(" ", text).replace("|", " ")
    return [t for t in text.split() if not _LAYOUT.match(t)]


def vote_page(texts: list[str], rejected: list | None = None) -> list[dict]:
    """One page's transcriptions, voted as ONE token stream.

    Models disagree on line breaks and table layout far more than on words,
    and ``ocr.apply_vision`` takes line geometry from Tesseract anyway.
    """
    readings = [tokens_of(t) for t in texts]
    # anchor on the MEDOID reading: a model that gave up on a page ("[?]" x
    # 12 lines) must not be the sequence the other two are aligned onto
    def closeness(i):
        return sum(SequenceMatcher(None, readings[i], readings[j], autojunk=False).ratio()
                   for j in range(len(readings)) if j != i)
    a = max(range(len(readings)), key=closeness)
    rej: list = []
    toks = vote_line_tokens([readings[a]] + readings[:a] + readings[a + 1:], rej)
    # Rescue what position-based voting mistook for absence.  Forms are read
    # in different orders (sidebar first or last), so a stream diff "rejects"
    # text two readings DO carry, just elsewhere.  The order-free majority is
    # the per-token median count across the readings: restore the shortfall
    # at the rejected position, reject only the true surplus.
    counts = [Counter(r) for r in readings]
    have = Counter(t["text"] for t in toks)
    restored = []
    for pos, run in rej:
        for w in run:
            if have[w] < sorted(c[w] for c in counts)[(len(counts) - 1) // 2]:
                have[w] += 1
                restored.append((pos, {"text": w, "votes": 2, "alts": [],
                                       "reordered": True}))
            elif rejected is not None:
                rejected.append(w)
    for pos, t in reversed(restored):    # reversed keeps earlier positions valid
        t["a"] = toks[pos - 1]["a"] if 0 < pos <= len(toks) else 0
        toks.insert(pos, t)
    # which printed line (of the anchor reading) each token belongs to
    line_of = [li for li, ln in enumerate(texts[a].splitlines()) for _ in tokens_of(ln)]
    for t in toks:
        if "[?]" in t["text"]:
            t["votes"] = 1          # "illegible" is never an accepted reading
        t["line"] = line_of[t.pop("a")] if line_of else 0
    return toks


def group_lines(toks: list[dict]) -> list[dict]:
    lines: list[dict] = []
    for t in toks:
        if not lines or lines[-1]["line"] != t["line"]:
            lines.append({"line": t["line"], "tokens": []})
        lines[-1]["tokens"].append(t)
    return lines


def rulings_path(pdf: str) -> Path:
    return Path(pdf + ".vision.rulings.json")


def apply_rulings(page: str, toks: list[dict], rulings: dict) -> list[dict]:
    """Human (image-checked) decisions, keyed by token index.

    ``expect`` pins what the vote produced there, so a ruling can never land
    on a different token after the raw transcriptions change.
    """
    ruled = dict(rulings.get(page, {}))
    verified = ruled.pop("verified", False)
    for idx, r in ruled.items():
        t = toks[int(idx)]
        if t["text"] != r["expect"]:
            raise SystemExit(f"p{page} #{idx}: ruling expects {r['expect']!r}, "
                             f"vote now says {t['text']!r} -- re-rule it")
        t["text"] = r["text"]          # "" deletes; "X Y" also inserts Y after X
        if r.get("review"):
            # best reading from the image, still not certain: stays flagged
            t["alts"] = [a for a in t.get("alts", []) + [r["expect"]] if a != r["text"]]
        else:
            t["ruled"] = r["text"]
    if verified:
        # the whole page was proofread against the image, token by token
        for t in toks:
            t.setdefault("ruled", t["text"])
    return [t for t in toks if t["text"]]


def cmd_transcribe(a) -> None:
    pages = [int(p) for p in a.pages.split(",")] if a.pages else body_scanned_pages(a.pdf)
    jobs = [(p, m) for p in pages for m in a.models]
    with ThreadPoolExecutor(8) as ex:
        futs = [ex.submit(transcribe_one, a.pdf, p, m) for p, m in jobs]
        for (p, m), fut in zip(jobs, futs):
            try:
                print(f"p{p} {m}: {len(fut.result())} chars")
            except Exception as e:
                print(f"p{p} {m}: FAILED {e}")


def cmd_vote(a) -> None:
    pages = [int(p) for p in a.pages.split(",")] if a.pages else body_scanned_pages(a.pdf)
    rulings = json.loads(rulings_path(a.pdf).read_text()) if rulings_path(a.pdf).exists() else {}
    old = sidecar_path(a.pdf)
    # --pages re-votes those pages INTO the existing sidecar, never drops others
    side = (json.loads(old.read_text()) if a.pages and old.exists()
            else {"models": a.models, "pages": {}})
    for p in pages:
        # a reader that failed (credits, provider outage) is simply absent:
        # with two readers every disagreement is a split and gets a human
        # ruling against the image, which is the third vote
        models = [m for m in a.models if raw_path(a.pdf, p, m).exists()]
        # a human transcription from zoomed crops replaces the FIRST listed
        # model -- on ITR p684 that is Sonnet, which returned 12 lines of "[?]"
        if raw_path(a.pdf, p, HUMAN).exists():
            models = models[1:] + [HUMAN] if len(models) >= 3 else models + [HUMAN]
        texts = [raw_path(a.pdf, p, m).read_text() for m in models]
        rejected: list[str] = []
        toks = apply_rulings(str(p), vote_page(texts, rejected), rulings)
        split = [i for i, t in enumerate(toks) if t["votes"] < 2 and "ruled" not in t]
        side["pages"][str(p)] = {"lines": group_lines(toks), "splits": len(split),
                                 "rejected": rejected, "models": models}
        if str(p) in rulings:
            side["pages"][str(p)]["adjudicator"] = ADJUDICATOR
        print(f"p{p}: {len(toks)} tokens, {len(split)} unresolved")
    sidecar_path(a.pdf).write_text(json.dumps(side, ensure_ascii=False, indent=1))


def _demo() -> None:
    v = vote_line_tokens([["Rule", "5(1)", "tax"], ["Rule", "5(l)", "tax"],
                          ["Rule", "5(1)", "tax"]])
    assert [t["text"] for t in v] == ["Rule", "5(1)", "tax"], v
    assert v[1]["votes"] == 2 and v[1]["alts"] == ["5(l)"], v
    v = vote_line_tokens([["a", "b"], ["a", "x", "b"], ["a", "x", "b"]])
    assert [t["text"] for t in v] == ["a", "x", "b"], v        # 2-vote insertion
    rej: list = []
    v = vote_line_tokens([["a", "junk", "b"], ["a", "b"], ["a", "b"]], rej)
    assert [t["text"] for t in v] == ["a", "b"] and rej == [(1, ["junk"])], v
    rej = []
    v = vote_line_tokens([["a", "b"], ["a", "x", "b"], ["a", "b"]], rej)
    assert [t["text"] for t in v] == ["a", "b"] and rej == [(1, ["x"])], v
    # reordered, not absent: B and C read the sidebar first, A read it last
    rej = []
    v = vote_page(["x y s1 s2", "s1 s2 x y", "s1 s2 x y"], rej)
    assert sorted(t["text"] for t in v) == ["s1", "s2", "x", "y"], v
    v = vote_page(["Rule 5\nof tax", "Rule 5 of tax", "Rule 5\nof tax"])
    assert [(t["text"], t["line"]) for t in v] == [("Rule", 0), ("5", 0), ("of", 1),
                                                   ("tax", 1)], v
    # one model's duplication stays outvoted
    v = vote_page(["a b", "a b b b", "a b"], [])
    assert [t["text"] for t in v] == ["a", "b"], v
    v = vote_line_tokens([["p", "q"], ["r", "q"], ["s", "q"]])
    assert v[0]["votes"] == 1, v                               # three-way split
    print("vision_ocr demo ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("transcribe", "vote"):
        s = sub.add_parser(name)
        s.add_argument("pdf")
        s.add_argument("--pages")
        s.add_argument("--models", type=lambda s: s.split(","), default=DEFAULT_MODELS)
    sub.add_parser("demo")
    a = ap.parse_args()
    {"transcribe": cmd_transcribe, "vote": cmd_vote, "demo": lambda _: _demo()}[a.cmd](a)

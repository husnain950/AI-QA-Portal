"""Dual-engine OCR for scanned pages -- every uncertain character is auditable.

The output of this pipeline is legally binding tax law, so a *silent* OCR
corruption is the worst defect available: Tesseract reading ``99A`` as ``994A``
turns one statutory cross-reference into another with no trace.  A single
recogniser cannot tell you that happened -- its own ``x_wconf`` was 95 on the
corrupted token.

So every scanned page is read by **two independent recognisers** with
uncorrelated error models -- Tesseract 5 (feature/LSTM, `hocr`) and RapidOCR
(ONNX, PP-OCRv4) -- and the two readings are compared token by token:

* both engines agree  -> accept, ``conf == "agreed"``
* they disagree       -> accept the higher-confidence reading, set
  ``needs_review``, and keep *both* readings on the token so a reviewer (and
  ``reports/ocr-disagreements-<act>.md``) can see exactly what was in doubt
* the page's confidence is the **inter-engine agreement rate**, not either
  engine's self-report, and that is what the fidelity floor gates on

Geometry always comes from Tesseract: hOCR gives a per-word ``bbox`` and the
line's ``x_size``, while RapidOCR only detects text *lines*.  RapidOCR is the
second opinion on the *characters*; Tesseract owns the layout.

What hOCR does **not** give is a font name or a bold flag, so words returned
here carry ``fontname=None`` -- see ``reports/m4-ocr-handoff.md`` for the one
guard that needs in ``builder._bold_title``.

Both engines are imported lazily, inside the functions that use them, so the
Phase-1 (text-layer) pipeline never pays for onnxruntime.

Self-check: ``python -m acts_ingest.ocr``.
"""

from __future__ import annotations

import difflib
import hashlib
import io
import json
import os
import re
import string
import subprocess
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

# --------------------------------------------------------------------------
# tunables -- all measured, see reports/ocr-exclusions.md
# --------------------------------------------------------------------------

#: a page with less real text than this is a scan (see ``page_needs_ocr``)
MIN_TEXT_CHARS = 200
#: render resolution; 300 is where Tesseract's confidence plateaus on this
#: corpus (300/400/500 x psm auto/6/4 moved mean confidence 90.5 -> 91.5 only)
DEFAULT_DPI = 300
#: a file is admitted only if mean inter-engine agreement is at least this
AGREEMENT_FLOOR = 85.0
#: ... and at most this share of tokens are low-confidence
LOW_CONF_SHARE_CEILING = 15.0
#: a token is "low confidence" when the accepted engine scored it below this
LOW_CONF = 60.0

_TESS_ARGS = ["tesseract", "stdin", "stdout", "--dpi", "%d",
              "-l", "eng", "hocr", "-c", "hocr_font_info=1"]

# Length-preserving canonicalisation (1:1 chars, so index maps stay valid).
# Quote/dash *shape* differences between the engines are not disagreements
# about the law; ``,`` vs ``.`` vs ``;`` very much is (tax rates), so those
# are deliberately NOT folded away.
_CANON = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"', "`": "'",
    "–": "-", "—": "-", "−": "-", "―": "-",
})


def _norm(s: str) -> str:
    return s.translate(_CANON).lower()


# --------------------------------------------------------------------------
# 1. the trigger
# --------------------------------------------------------------------------

def page_needs_ocr(page, min_chars: int = MIN_TEXT_CHARS) -> bool:
    """True when this pdfplumber page carries no usable text layer.

    **Per page, never per file.**  ``Finance Acts/Finance Act 2025.pdf`` has a
    real 58-character running-header text layer stamped over a scanned body:
    a per-file test ("does the document extract any text?") says "not a scan"
    and silently ships an empty Act.
    """
    try:
        text = page.extract_text() or ""
    except Exception:                                   # pragma: no cover
        return True
    return len(text.strip()) < min_chars


# --------------------------------------------------------------------------
# 2. the two engines
# --------------------------------------------------------------------------

def render_png(pdf_path: str, pageno: int, dpi: int = DEFAULT_DPI) -> bytes:
    """Render 1-based ``pageno`` to PNG bytes (no temp files anywhere)."""
    import pypdfium2

    doc = pypdfium2.PdfDocument(pdf_path)
    try:
        img = doc[pageno - 1].render(scale=dpi / 72.0).to_pil()
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()
    finally:
        doc.close()


_WORD_CLASSES = ("ocrx_word",)
_LINE_CLASSES = ("ocr_line", "ocr_header", "ocr_textfloat", "ocr_caption")
_BBOX_RE = re.compile(r"bbox (\d+) (\d+) (\d+) (\d+)")
_WCONF_RE = re.compile(r"x_wconf (-?[\d.]+)")
_XSIZE_RE = re.compile(r"x_size ([\d.]+)")
_FSIZE_RE = re.compile(r"x_fsize ([\d.]+)")


def tesseract_words(png: bytes, dpi: int = DEFAULT_DPI) -> list[dict]:
    """hOCR words in *image pixels*: ``text, box, conf, size_px, line``.

    ``line`` is the hOCR ``ocr_line`` index -- the grouping RapidOCR's
    line-level boxes are aligned against.  ``size_px`` comes from the line's
    ``x_size`` because this Tesseract build emits no per-word ``x_fsize``
    even with ``hocr_font_info=1`` (verified: 0 occurrences on a real page).
    """
    proc = subprocess.run([a % dpi if "%d" in a else a for a in _TESS_ARGS],
                          input=png, capture_output=True)
    if proc.returncode != 0:                            # pragma: no cover
        raise RuntimeError(f"tesseract failed: {proc.stderr[-400:]!r}")
    root = ET.fromstring(proc.stdout)
    words: list[dict] = []
    for li, line in enumerate(el for el in root.iter()
                              if el.get("class") in _LINE_CLASSES):
        title = line.get("title") or ""
        m = _XSIZE_RE.search(title)
        size_px = float(m.group(1)) if m else None
        for w in line.iter():
            if w.get("class") not in _WORD_CLASSES:
                continue
            wt = w.get("title") or ""
            box = _BBOX_RE.search(wt)
            text = "".join(w.itertext()).strip()
            if not text or box is None:
                continue
            conf = _WCONF_RE.search(wt)
            fs = _FSIZE_RE.search(wt)
            words.append({
                "text": text,
                "box": tuple(int(v) for v in box.groups()),
                "conf": float(conf.group(1)) if conf else 0.0,
                "size_px": float(fs.group(1)) if fs else size_px,
                "line": li,
            })
    return words


_ENGINE = None


def _rapid_engine():
    """The RapidOCR session, built once per process (~4s of model load)."""
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR  # lazy: heavy import
        _ENGINE = RapidOCR()
    return _ENGINE


#: RapidOCR's detector requires both sides to be a multiple of this
_DET_ALIGN = 32


def _align_for_det(img) -> tuple:
    """Do RapidOCR's 32-alignment ourselves when it is a DOWNSCALE.

    Returns ``(image, sx, sy)``.  The scales matter: RapidOCR normally maps its
    detected boxes back to the ORIGINAL image through the ratios its own resize
    computed, so when we resize first its boxes come back in the aligned frame
    instead -- up to 32 px adrift at the far edge, which would silently
    mis-pair RapidOCR lines against Tesseract's (Tesseract reads the unmodified
    PNG).  The caller divides the boxes back out.

    RapidOCR is configured ``limit_type=min, limit_side_len=736``; every page
    here is far larger than 736, so its "resize" is nothing but
    ``round(side / 32) * 32`` -- a sub-percent rescale.  When that rounds DOWN
    on *both* axes, OpenCV 5.0.0's KleidiCV 26.03 ``resize_generic_stripe_u8``
    kernel reads out of bounds and the process dies with SIGSEGV, taking the
    whole conversion with it.  Ledger P13.

    The crash was previously recorded as an out-of-memory kill (P12).  It is
    not: it reproduces at 6.8 GB free in three lines, and it is deterministic
    per geometry -- ``(3402, 2433, 3) -> (2432, 3392)`` always dies, while
    2434 and 2436 wide are fine and 2435 and 2441 are not.  The boundary is
    non-monotone in width, so a predicate that tries to name the crashing
    geometries would be a guess; instead this covers the whole down-rounding
    region, which is where the unsafe kernel is reachable at all.

    Do not narrow this to "the pages that crash".  Measuring which geometries
    die needs the EXACT rendered size -- pypdfium2 renders at
    ``ceil(size * dpi/72)`` and swaps the axes on 90/270 rotation -- and a
    first attempt at that arithmetic was off by one pixel, which reported
    Finance Act 2013 as having no crashing page while holding the very stack
    trace that named page 46 (2433x3402 -> 2432x3392).  A guard whose
    correctness turns on getting a rounding mode right is the wrong guard.

    Doing the resize in float32 avoids the u8 kernel entirely.  Measured
    against reference INTER_LINEAR on an even-width source it is the closest
    of every available bypass -- max deviation 2/255 on 1.1% of pixels, better
    than INTER_AREA (2/255, 1.2%) and two-step u8 (2/255, 1.3%), and far
    better than INTER_NEAREST (253) or INTER_CUBIC (51).  Up-rounding and
    already-aligned pages are left untouched, so their recognition is
    byte-identical to before: 320 of 13,394 corpus pages (2.4%) over 11 files
    take this path, and 68 of those 320 are geometries a probe can kill on
    demand.  Only the 320 needed their cache entries cleared (123 existed).

    Dropping the alignment altogether was tried and rejected -- it is NOT a
    free fidelity win.  Feeding the detector an unresampled 32-padded page
    changes recognition in both directions on the same page (it recovers
    ``of Pakistan, ISLAMABAD.`` but corrupts ``In the Sales Tax Act`` to
    ``ln the Sales Tax Act``), so it trades one set of errors for another.
    """
    import cv2
    import numpy as np

    h, w = img.shape[:2]
    if min(h, w) < 736:                     # RapidOCR would scale UP, not align
        return img, 1.0, 1.0
    rh = int(round(h / _DET_ALIGN) * _DET_ALIGN)
    rw = int(round(w / _DET_ALIGN) * _DET_ALIGN)
    if not (rh < h and rw < w):             # up-rounding never reaches the bug
        return img, 1.0, 1.0
    out = cv2.resize(img.astype(np.float32), (rw, rh),
                     interpolation=cv2.INTER_LINEAR)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8), rw / w, rh / h


def rapidocr_lines(png: bytes) -> list[dict]:
    """RapidOCR text lines in *image pixels*: ``text, box, conf``."""
    import numpy as np
    from PIL import Image

    img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
    img, sx, sy = _align_for_det(img)
    result, _elapse = _rapid_engine()(img)
    lines = []
    for quad, text, score in (result or []):
        xs = [float(p[0]) / sx for p in quad]
        ys = [float(p[1]) / sy for p in quad]
        lines.append({"text": text,
                      "box": (min(xs), min(ys), max(xs), max(ys)),
                      "conf": float(score) * 100.0})
    return lines


# --------------------------------------------------------------------------
# 3. alignment
# --------------------------------------------------------------------------

def _inter(a, b) -> float:
    """Intersection area of two ``(x0, top, x1, bottom)`` boxes."""
    ox = min(a[2], b[2]) - max(a[0], b[0])
    oy = min(a[3], b[3]) - max(a[1], b[1])
    return ox * oy if ox > 0 and oy > 0 else 0.0


def _index_map(a: str, b: str) -> list[int]:
    """``m[i]`` = position in ``b`` corresponding to ``a[i]`` (len+1 entries).

    Exact inside ``equal`` runs, linearly interpolated inside a
    replace/insert/delete block -- which is what lets a *word*'s character
    span be projected onto the other engine's reading even when the two
    tokenised the line differently (``Ordinance, 2001`` vs
    ``Ordinance,2001``).
    """
    m = [0] * (len(a) + 1)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, a, b, autojunk=False).get_opcodes():
        n = i2 - i1
        for k in range(n):
            m[i1 + k] = j1 + k if tag == "equal" else j1 + round((j2 - j1) * k / n)
        m[i2] = j2
    m[len(a)] = len(b)
    return m


def _pair_lines(tess_lines: dict, rapid: list[dict]) -> tuple[dict, list[int]]:
    """Assign every RapidOCR line to the Tesseract line it overlaps most.

    Many-to-one on purpose: the two detectors disagree about where a line
    starts and stops (RapidOCR routinely splits one printed line into two or
    three boxes, and puts the clause marker in a box of its own), so a 1:1
    matching leaves real text unpaired and manufactures disagreements.
    """
    groups: dict[int, list[dict]] = {}
    unpaired: list[int] = []
    for ri, r in enumerate(rapid):
        rmid = (r["box"][1] + r["box"][3]) / 2.0
        best, bl = 0.0, None
        for li, lb in tess_lines.items():
            if not lb[1] - 4 <= rmid <= lb[3] + 4:
                continue                     # a different printed line
            v = _inter(lb, r["box"])
            if v > best:
                best, bl = v, li
        if bl is None:
            unpaired.append(ri)
        else:
            groups.setdefault(bl, []).append(r)
    return groups, unpaired


@dataclass
class PageOCR:
    """One OCR'd page: its words plus the numbers the fidelity floor needs."""
    page: int
    words: list[dict]
    agreed: int = 0
    total: int = 0
    low_conf: int = 0
    missed: list[str] = field(default_factory=list)   # text only RapidOCR saw
    repairs: list[dict] = field(default_factory=list)
    error: str | None = None         # set when the page could not be OCR'd

    @property
    def agreement(self) -> float:
        return 100.0 * self.agreed / self.total if self.total else 0.0


#: A glued run of PROSE, as opposed to one long chemical name.  Ledger P45.
#: Both jams that survived the P23 spacing fix are one engine reading a
#: MULTI-COLUMN table row straight across and emitting it as a single token,
#: while the other engine read only the cell:
#:
#:   PSW 2021 p13  tesseract 'malicious'
#:                 rapidocr  'maliciousmayextendtofouryearsandfine'  (conf 91.6)
#:   FA2025        'roundnutsshelledweatherornotbroken', beside a correctly
#:                 spaced 'weather or not broken' on the next line
#:
#: Confidence alone picked the glued one.  A recogniser that has run two columns
#: together is not more right for being more sure, and the corpus's genuine long
#: tokens are chemical names -- ``bromochlorodifluoromethane`` (26),
#: ``Aminohydroxynaphthalenesulphonic`` (32) -- which contain no English function
#: words.  Verified over both sets: 0 of 11 chemical names contain two of these
#: words and every glued sentence contains at least two.
#:
#: Deliberately a SEPARATE copy of the predicate ``tests.invariants._is_jam``
#: uses.  Sharing it would let one bug hide itself on both sides of the gate.
_GLUED_MIN = 25
_GLUED_WORDS = ("the", "and", "not", "shall", "may", "with", "which", "that",
                "this", "from", "been", "any", "tax", "per", "cent", "rupees",
                "year", "person", "fine", "extend", "purpose", "who", "fails",
                "means", "under", "said", "such")


def _is_glued_run(text: str) -> bool:
    """Whether a reading is a run of glued English prose, not one long word."""
    low = (text or "").strip().lower()
    if len(low) < _GLUED_MIN or not low.isalpha():
        return False
    return sum(1 for w in _GLUED_WORDS if w in low) >= 2


def _ran_columns_together(alt: str, own: str) -> bool:
    """Whether ``alt`` is ``own`` with a neighbouring column glued onto it.

    The prefix requirement is what makes this safe, and it was added after
    measuring.  Rejecting every glued reading in favour of the other engine's
    would have swapped in nonsense: over the 4,130 cached pages exactly **10
    words** have a glued winner, and on 9 of them the other engine is no better
    -- ``roundnutsshelledweatherornotbroken`` is opposed by
    ``reilianieceannny``, ``stitutionsandotherpersonsd`` by ``SA``,
    ``recoveredbytheAuthorityshallbecreditedtotheFe`` by ``|``.  Those are two
    engines both failing on a hard region, which is a source defect, not a
    tie-break this code can win.

    Only where the shorter reading is a PREFIX of the longer is the evidence
    unambiguous -- the engine read the cell and then kept going into the next
    column: ``malicious`` / ``maliciousmayextendtofouryearsandfine`` on page 13
    of the Pakistan Single Window Act, which is the one case in the corpus.
    """
    if not (_is_glued_run(alt) and not _is_glued_run(own)):
        return False
    own = (own or "").strip()
    return bool(own) and alt.strip().lower().startswith(own.lower())


def align(tess: list[dict], rapid: list[dict], pageno: int = 1,
          dpi: int = DEFAULT_DPI) -> PageOCR:
    """Merge the two engines' readings into pdfplumber-shaped word dicts.

    Pure function of the two engines' output -- no PDF, no models -- which is
    what makes the agreement/repair logic testable on recorded token pairs.
    """
    scale = 72.0 / dpi
    lines: dict[int, list[dict]] = {}
    for w in tess:
        lines.setdefault(w["line"], []).append(w)
    boxes = {}
    for li, ws in lines.items():
        ws.sort(key=lambda w: w["box"][0])
        boxes[li] = (min(w["box"][0] for w in ws), min(w["box"][1] for w in ws),
                     max(w["box"][2] for w in ws), max(w["box"][3] for w in ws))

    groups, unpaired = _pair_lines(boxes, rapid)
    out = PageOCR(page=pageno, words=[])

    for li in sorted(lines, key=lambda k: (boxes[k][1], boxes[k][0])):
        ws = lines[li]
        # left-to-right: the RapidOCR boxes of one printed line, in reading
        # order (sorting by y first scrambles marker/body, whose boxes sit at
        # slightly different heights, and corrupts the whole line's diff)
        segs = sorted(groups.get(li, []), key=lambda r: r["box"][0])
        b_raw, b_norm, b_conf = [], [], []
        for r in segs:
            for ch in r["text"]:
                if ch.isspace():
                    continue
                b_raw.append(ch)
                b_norm.append(_norm(ch))
                b_conf.append(r["conf"])
        b_raw_s, b_norm_s = "".join(b_raw), "".join(b_norm)

        spans, a_raw, a_norm = [], [], []
        for w in ws:
            start = len(a_norm)
            for ch in w["text"]:
                if ch.isspace():
                    continue
                a_raw.append(ch)
                a_norm.append(_norm(ch))
            spans.append((start, len(a_norm)))
        a_norm_s = "".join(a_norm)
        m = _index_map(a_norm_s, b_norm_s) if segs else None

        for (s, e), w in zip(spans, ws):
            if m is None:
                alt, alt_conf = None, 0.0
            else:
                alt = b_raw_s[m[s]:m[e]]
                pos = [b_conf[i] for i in range(m[s], min(m[e], len(b_conf)))]
                alt_conf = min(pos) if pos else 0.0
            agreed = alt is not None and _norm(alt) == a_norm_s[s:e]
            text, conf = w["text"], w["conf"]
            # Never upgrade TO a glued prose run.  RapidOCR reads multi-column
            # tariff rows as one token (FA2025 ``roundnutsshelledweatherornotbroken``,
            # conf 84) while Tesseract keeps a short garbage token; confidence
            # alone preferred the jam and failed ``inv_no_jammed_words``.
            # ``_ran_columns_together`` only catches the prefix case
            # (``malicious`` / ``maliciousmayextend...``); this rejects the rest.
            prefer_alt = (not agreed and alt and alt_conf > conf
                          and not _ran_columns_together(alt, w["text"]))
            if prefer_alt and _is_glued_run(alt) and not _is_glued_run(w["text"]):
                # #region agent log
                try:
                    import json as _json
                    import time as _time
                    open("/Users/muhammad.husnain/Downloads/code/crx/.cursor/debug-661395.log", "a").write(
                        _json.dumps({"sessionId": "661395", "hypothesisId": "C",
                                     "location": "ocr.py:align", "message": "reject_glued_alt",
                                     "data": {"alt": (alt or "")[:50], "own": (w.get("text") or "")[:50],
                                              "alt_conf": alt_conf, "own_conf": conf},
                                     "timestamp": int(_time.time() * 1000)}) + "\n")
                except Exception:
                    pass
                # #endregion
                prefer_alt = False
            if prefer_alt:
                # higher-confidence reading wins -- but the token still
                # carries both readings and needs_review either way
                text, conf = alt, alt_conf
            out.total += 1
            if agreed:
                out.agreed += 1
            if conf < LOW_CONF:
                out.low_conf += 1
            x0, top, x1, bottom = (v * scale for v in w["box"])
            # size must never be None: pagemodel does round(float(w["size"]))
            size_px = w["size_px"] or (w["box"][3] - w["box"][1]) / 0.72
            out.words.append({
                "text": text,
                "x0": x0, "x1": x1, "top": top, "bottom": bottom,
                "size": round(size_px * scale, 1),
                "fontname": None,          # hOCR carries no font / no bold
                "conf": "agreed" if agreed else round(conf, 1),
                "needs_review": not agreed,
                "page": pageno,
                "tesseract": w["text"],
                "rapidocr": alt,
                "conf_tesseract": round(w["conf"], 1),
                "conf_rapidocr": round(alt_conf, 1),
            })

    _mark_space_before(out.words)

    # Text only RapidOCR saw is a fidelity failure too (Tesseract dropped a
    # line), so it counts against the page even though it yields no word.
    for ri in unpaired:
        toks = rapid[ri]["text"].split()
        out.total += len(toks)
        out.missed.append(rapid[ri]["text"])
    return out


def _mark_space_before(words: list[dict]) -> None:
    """Every recognised token is a separate word: ``_space_before`` is always True.

    ``pagemodel._mark_space_before`` derives this from ``page.chars``, which is
    empty on a scanned page -- every word would come back "no space before" and
    the marker/continuation logic that reads it would misfire.  This used to
    substitute a geometric test (a gap of at least a quarter of the point size),
    and that was the wrong question to ask of hOCR: **Tesseract emits one
    ``ocrx_word`` per whitespace-delimited token**, so two consecutive words on a
    line had a space between them by construction, whatever their boxes say.

    Measured on the Benami Transactions (Prohibition) Act 2017 cover, where the
    display face sets tight: real inter-word gaps of 0.72-1.44 pt at size 10.6
    (threshold 2.65) were read as "no space", so ``builder._render_words`` glued
    the tokens and the output shipped ``to provideforprohibitiont ofholdingpraperty
    in benam``.  That is a jammed word in legally binding text -- it fails
    ``inv_no_jammed_words``, it makes the words unsearchable, and it cost three
    body words of conservation because the tokens no longer exist in the output.

    Trusting the recognition also disables ``pagemodel._merge_split_words``'s
    kerning and ordinal merges on scans, which is correct: both repair a
    TEXT-LAYER artifact (one word drawn as two font runs) that cannot occur in
    hOCR, where the tokenisation is the recogniser's own.
    """
    for w in words:
        w["_space_before"] = True


#: where recognised pages are cached; override with ACTS_OCR_CACHE, "" disables
CACHE_DIR = os.environ.get(
    "ACTS_OCR_CACHE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 ".ocrcache"))
#: bump when anything that changes recognised OUTPUT changes (engine args, the
#: alphabet tables, align, repair_enumerators) -- otherwise a stale entry would
#: be served for code that would now read the page differently
#: "2" (2026-08-08): ``_mark_space_before`` now trusts the recogniser's own
#: tokenisation instead of a geometric gap test, so every cached page's
#: ``_space_before`` flags are stale -- and a stale entry would keep shipping the
#: jammed words this fixed ("provideforprohibitiont").
#: P45 (2026-08-09) changed ``align`` and did NOT bump this, following P13's
#: precedent of invalidating a KNOWN region instead: the change can only affect a
#: word whose accepted reading is a glued run and whose other reading is its
#: prefix, and a census of all 4,130 cached pages found **2 such words, in 2
#: entries**, which were rewritten in place.  The rewrite was proved equivalent
#: to recognition -- one entry was deleted, re-OCR'd, and every word of the fresh
#: result compared equal to the rewritten one.  A blind bump would have
#: re-recognised ~1,570 pages to change two tokens.
CACHE_VERSION = "2"


def _cache_key(pdf_path: str, pageno: int, dpi: int, repair: bool) -> str:
    """Identity of one recognition: the FILE's content-ish identity plus params.

    Size+mtime rather than a content hash: hashing a 300 MB PDF on every page
    would cost more than it saves, while size+mtime changes whenever the source
    is replaced, which is the case that must invalidate.
    """
    try:
        st = os.stat(pdf_path)
        ident = f"{os.path.basename(pdf_path)}:{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        ident = pdf_path
    raw = f"{CACHE_VERSION}|{ident}|{pageno}|{dpi}|{int(repair)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_load(key: str) -> PageOCR | None:
    if not CACHE_DIR:
        return None
    try:
        with open(os.path.join(CACHE_DIR, f"{key}.json"), encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    return PageOCR(page=d["page"], words=d["words"], agreed=d["agreed"],
                   total=d["total"], low_conf=d["low_conf"],
                   missed=d["missed"], repairs=d["repairs"])


def _cache_store(key: str, r: PageOCR) -> None:
    if not CACHE_DIR or r.error:
        return                              # never cache a failed recognition
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = os.path.join(CACHE_DIR, f"{key}.json.tmp{os.getpid()}")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"page": r.page, "words": r.words, "agreed": r.agreed,
                       "total": r.total, "low_conf": r.low_conf,
                       "missed": r.missed, "repairs": r.repairs}, fh)
        os.replace(tmp, os.path.join(CACHE_DIR, f"{key}.json"))
    except OSError:
        pass                                # a cache is an optimisation, never a
        #                                     reason for a conversion to fail


def ocr_page(pdf_path: str, pageno: int, dpi: int = DEFAULT_DPI,
             repair: bool = True) -> PageOCR:
    """Run both engines on one page and return the merged :class:`PageOCR`.

    Cached on disk, because recognition is by far the most expensive thing this
    corpus does and it does not depend on any of the code being iterated on.
    Measured: ~5s per page warm and uncontended (render 0.56s, Tesseract 1.72s,
    RapidOCR ~4.2s), and Finance Act 2025's 289 pages were recognised TWICE in
    one day -- roughly an hour of compute -- for two conversions that differed
    only in ``discover.py`` and ``pipeline.py``, neither of which can affect what
    the engines read.

    The key covers the source file's identity and every parameter that changes
    the output, so replacing the PDF or changing the dpi re-recognises.  A cache
    miss, an unreadable entry or an unwritable directory all degrade to simply
    doing the work -- this must never be a reason a conversion fails.
    """
    key = _cache_key(pdf_path, pageno, dpi, repair)
    hit = _cache_load(key)
    if hit is not None:
        return hit
    png = render_png(pdf_path, pageno, dpi)
    result = align(tesseract_words(png, dpi), rapidocr_lines(png), pageno, dpi)
    if repair:
        result.words, result.repairs = repair_enumerators(result.words)
    _cache_store(key, result)
    return result


def ocr_words(pdf_path: str, pageno: int, dpi: int = DEFAULT_DPI) -> list[dict]:
    """Words for one scanned page, shaped like ``page.extract_words()``.

    Keys ``text, x0, x1, top, bottom, size, fontname`` (``fontname`` always
    ``None``) plus ``conf`` (``"agreed"`` or the accepted engine's score),
    ``needs_review``, and both engines' readings.  Coordinates are PDF points.
    """
    return ocr_page(pdf_path, pageno, dpi).words


# --------------------------------------------------------------------------
# 4. sequence-aware enumerator repair
# --------------------------------------------------------------------------

# Tesseract mangles the *enumerator alphabet* on degraded scans in ways no
# DPI or PSM sweep fixes: (a)->(al, (b)->{b}/(bj, (d)->(dl], (e)->[et]/je].
# Inside a run of clause markers the sequence is known, so an off-sequence
# marker-shaped token can be repaired *and logged*.  Body words and digits are
# never touched: 99A -> 994A is not recoverable by sequence, and a plausible
# guess is strictly worse than a flagged error.
_MARKER_RE = re.compile(r"^[\(\[\{|<]?\s*([A-Za-z0-9]{1,4})\s*[\)\]\}|JjlI!,.;:>]*$")
_BRACKETISH = set("([{|<)]}>")
_ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
          "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx"]
_ROMAN_CHARS = set("ivxl")
_ALPHABETS = [
    ("lower", list(string.ascii_lowercase)),
    ("roman", _ROMAN),
    ("digit", [str(n) for n in range(1, 100)]),
    ("upper", list(string.ascii_uppercase)),
]
#: only a token the engines already doubted is a repair candidate
_REPAIR_CONF = 80.0


def _marker_core(text: str) -> str | None:
    """The alphanumeric core of a marker-shaped token, else ``None``.

    Requires a bracket-ish character, so a bare ``99A`` or ``994A`` -- the
    corruption class that must stay flagged, never guessed -- can never be a
    candidate.
    """
    if not any(ch in _BRACKETISH for ch in text):
        return None
    m = _MARKER_RE.match(text)
    return m.group(1) if m else None


#: any well-formed short marker value -- deliberately generous, because this
#: only decides what is LEFT ALONE.  "(aa)", "(ii)", "(45)", "(XV)" are all real
#: enumerators in this corpus, and a run of "(1) (2) (3)" containing a printed
#: "(b)" is a fact about the source, not something to renumber.
_VALID_CORE_RE = re.compile(r"[A-Za-z]{1,3}|\d{1,3}")


def _canonical(text: str, core: str) -> bool:
    """A well-formed marker whose value is a plausible enumerator: ``(a)``.

    Never rewritten, in or out of sequence, and **regardless of which alphabet
    the column voted for** -- rewriting a printed ``(b)`` to ``(5)`` because it
    sits in a numeric column (measured: RTI 2017 p12) is precisely the
    plausible-guess-worse-than-a-flagged-error failure.
    """
    return text == f"({core})" and _VALID_CORE_RE.fullmatch(core) is not None


def _anchor(w: dict, core: str, alpha: list[str]) -> bool:
    """Can this token *define* the sequence?

    Only if it is well-formed **and both engines read it the same way**.  A
    canonical shape alone is not enough: on a degraded page RapidOCR happily
    reads the printed ``(c)`` as a confident, perfectly-shaped ``(e)``, and
    ``align`` accepts it because it outscored Tesseract's ``(c}``.  Trusting
    that as an anchor is how a repair pass invents ``(b)`` where the source
    prints ``(e)`` -- measured on Benami 2017 p4, which is exactly the class of
    silent corruption this module exists to prevent.
    """
    return (core in alpha and _canonical(w["text"], core)
            and not w.get("needs_review") and w.get("conf") == "agreed")


def repair_enumerators(words: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rewrite off-sequence *structural enumerators* in place; log every one.

    A token is repaired only when all four hold:

    1. it is marker-shaped and bracketed (never a bare word or number),
    2. it sits in a column holding at least two *agreed* well-formed markers
       (which is what proves the column *is* an enumerator column), with such
       an anchor in its own segment to locate it -- see :func:`_anchor`,
    3. its shape is mangled -- a clean ``(f)`` that is merely out of sequence
       is left exactly as printed, because the *source* may say ``(f)``,
    4. at least one engine doubted it (``needs_review`` or conf < 80).

    Two kinds of repair, and the order matters:

    ``shape``
        both engines imply the same value and differ only in the bracket
        glyphs (``{2]`` / ``[2]`` -> ``(2)``).  The sequence is *not* consulted
        -- it may never override a value both recognisers read.
    ``sequence``
        neither reading parses as an enumerator at all (``(zt)`` / nothing),
        so the position relative to an agreed anchor supplies the value.

    Returns ``(words, repairs)``; repaired tokens keep ``needs_review`` and
    gain a ``repair`` key holding the original reading.
    """
    # Structural enumerators start their printed line.  A bracketed token in
    # running text does not, which is what keeps a citation like "(XLIX of
    # 2001)" or "clauses (a) to (d)." out of the repair pass entirely -- both
    # are marker-shaped, and rewriting either would corrupt a cross-reference.
    lead = _line_leading(words)
    cands = [(i, c) for i, w in enumerate(words)
             if i in lead and (c := _marker_core(w["text"])) is not None]
    repairs: list[dict] = []
    if not cands:
        return words, repairs

    # Marker columns: same left edge (6pt buckets) == same nesting level, so
    # an outer (a),(b),(c) run is never mixed with an inner (i),(ii) run.
    # ponytail: fixed 6pt buckets, not clustering -- a column whose left edge
    # straddles a bucket boundary splits into two runs and simply gets fewer
    # anchors, i.e. fewer repairs.  Cluster if that ever costs a real repair.
    cols: dict[int, list[tuple[int, str]]] = {}
    for i, core in cands:
        cols.setdefault(int(words[i]["x0"] // 6), []).append((i, core))

    for _bucket, run in cols.items():
        run.sort(key=lambda t: words[t[0]]["top"])
        # Only *agreed* well-formed markers vote on the alphabet, and two of
        # them are the minimum: one lone "(a)" does not prove the
        # low-confidence token under it is an enumerator at all.
        name, alpha = _pick_alphabet(
            [c for i, c in run if _canonical(words[i]["text"], c)
             and not words[i].get("needs_review")])
        if alpha is None:
            continue
        # split at every restart (an anchor whose value does not advance)
        segments, cur, last = [], [], -1
        for i, core in run:
            idx = (alpha.index(core) if _anchor(words[i], core, alpha)
                   else None)
            if idx is not None:
                if idx <= last:
                    segments.append(cur)
                    cur = []
                last = idx
            cur.append((i, core))
        segments.append(cur)

        for seg in segments:
            anchors = [(p, alpha.index(core)) for p, (i, core) in enumerate(seg)
                       if _anchor(words[i], core, alpha)]
            if not anchors:
                continue
            taken = {idx for _, idx in anchors}
            for p, (i, core) in enumerate(seg):
                w = words[i]
                if _canonical(w["text"], core):
                    # Well-formed as printed -- and note there is NO alphabet
                    # test here: "(b)" inside a numeric run is what the source
                    # says, not a mis-numbered "(5)".
                    continue
                if not (w.get("needs_review") or
                        _conf_value(w) < _REPAIR_CONF):
                    continue                                   # both engines sure
                read = _read_values(w, alpha)
                if len(read) > 1:
                    continue         # engines read different values: leave it
                if read:
                    # The engines agree on the *value* and differ only in the
                    # bracket glyphs ("{2]" / "[2]").  Normalise the shape and
                    # nothing else -- the sequence must never override a value
                    # both recognisers actually read.  (Measured on Benami 2017
                    # p14, where a new section's "(2)" sat at sequence position
                    # 4 and arithmetic rewrote it to "(4)".)
                    expected, kind = read.pop(), "shape"
                else:
                    # Neither reading parses: only now may the known sequence
                    # supply the value, anchored on agreed markers.  And only
                    # for a core small enough to *be* a mangled marker: "(2018)"
                    # is marker-shaped and would otherwise be handed a sequence
                    # value, turning a year into a clause number.
                    if not (len(core) <= 2 or set(core.lower()) <= _ROMAN_CHARS):
                        continue
                    ap, aidx = min(anchors, key=lambda t: abs(t[0] - p))
                    want = aidx + (p - ap)
                    if not 0 <= want < len(alpha) or want in taken:
                        continue                 # can't place it: leave flagged
                    expected, kind = alpha[want], "sequence"
                    taken.add(want)
                repairs.append({
                    "page": w.get("page"), "x0": round(w["x0"], 1),
                    "top": round(w["top"], 1), "before": w["text"],
                    "after": f"({expected})", "alphabet": name, "kind": kind,
                    "tesseract": w.get("tesseract"), "rapidocr": w.get("rapidocr"),
                    "conf": w.get("conf"),
                })
                w["repair"] = w["text"]
                w["text"] = f"({expected})"
    return words, repairs


def _line_leading(words: list[dict]) -> set[int]:
    """Indices of the words that are leftmost on their printed line.

    6pt of tolerance because these scans are skewed about a degree, so one
    printed line's words differ in ``top`` by up to 5pt; body leading is ~13pt,
    so lines still cannot merge.
    """
    order = sorted(range(len(words)), key=lambda i: (words[i]["top"], words[i]["x0"]))
    leading, cur = set(), []
    for i in order:
        if cur and words[i]["top"] - words[cur[0]]["top"] > 6.0:
            leading.add(min(cur, key=lambda j: words[j]["x0"]))
            cur = []
        cur.append(i)
    if cur:
        leading.add(min(cur, key=lambda j: words[j]["x0"]))
    return leading


def _read_values(w: dict, alpha: list[str]) -> set[str]:
    """The enumerator values the two engines' readings actually imply.

    One value means they agree on *what* the marker is and differ only in the
    bracket glyphs; two means they read different markers, which no amount of
    sequence arithmetic is entitled to resolve.
    """
    out = set()
    for reading in (w.get("tesseract"), w.get("rapidocr"), w.get("text")):
        core = _marker_core(reading) if reading else None
        if core is None:
            continue
        for cand in (core, core.lower()):
            if cand in alpha:
                out.add(cand)
                break
    return out


def _conf_value(w: dict) -> float:
    c = w.get("conf")
    return 100.0 if c == "agreed" else float(c or 0.0)


def _pick_alphabet(cores: list[str]):
    """The alphabet most of a run's *agreed* markers belong to (>= 2 of them).

    Two minimum: with one, a mangled neighbour could be "repaired" from a
    single accidental match.  ``i`` is both a letter and a roman numeral, so
    the vote -- not a per-token guess -- decides which run this is.
    """
    best, name = None, None
    score = 1
    for nm, alpha in _ALPHABETS:
        hits = sum(1 for c in cores if c in alpha)
        if hits > score:
            best, name, score = alpha, nm, hits
    return name, best


# --------------------------------------------------------------------------
# 5. fidelity floor
# --------------------------------------------------------------------------

@dataclass
class Fidelity:
    """Whether a file may be shipped, and the numbers that decided it."""
    path: str
    pages: int = 0                  # pages that needed OCR
    blank: int = 0                  # ... of which held no text at all
    failed: list[int] = field(default_factory=list)   # ... of which errored
    tokens: int = 0
    mean_agreement: float = 0.0     # mean over pages of the agreement rate
    low_conf_share: float = 0.0     # share of tokens the engine itself doubted
    per_page: list[tuple[int, float, int]] = field(default_factory=list)
    missed: list[tuple[int, str]] = field(default_factory=list)
    disagreements: list[dict] = field(default_factory=list)
    repairs: list[dict] = field(default_factory=list)

    @property
    def admitted(self) -> bool:
        return (self.pages > 0
                and not self.failed
                and self.mean_agreement >= AGREEMENT_FLOOR
                and self.low_conf_share <= LOW_CONF_SHARE_CEILING)

    @property
    def reason(self) -> str:
        if not self.pages:
            return "no OCR pages"
        bad = []
        if self.failed:
            # A page that errored produced no tokens, which would otherwise
            # look exactly like a harmless blank page and could let a file in
            # on the strength of the pages that did work.
            bad.append(f"{len(self.failed)} page(s) failed to OCR: "
                       + ", ".join(str(p) for p in self.failed[:10]))
        if self.mean_agreement < AGREEMENT_FLOOR:
            bad.append(f"mean agreement {self.mean_agreement:.1f}% "
                       f"< {AGREEMENT_FLOOR:.0f}%")
        if self.low_conf_share > LOW_CONF_SHARE_CEILING:
            bad.append(f"low-confidence tokens {self.low_conf_share:.1f}% "
                       f"> {LOW_CONF_SHARE_CEILING:.0f}%")
        return "; ".join(bad) or "within floor"


def fidelity_of(path: str, pages: list[PageOCR]) -> Fidelity:
    """Aggregate per-page results into the admit/exclude decision.

    Note the aggregation is over **every** OCR'd page of the file, never a
    sample: a 40-page Act whose first 5 pages are clean and whose last 35 are
    a photocopy of a photocopy passes any sampled gate.
    """
    f = Fidelity(path=path, pages=len(pages))
    if not pages:
        return f
    # A page both engines read as empty is a genuinely blank leaf (every
    # Customs edition ends on one, and the trigger cannot tell blank from
    # scanned): it carries no risk, so it must not drag the mean to 0.
    read = [p for p in pages if p.total]
    f.blank = len(pages) - len(read)
    f.tokens = sum(p.total for p in read)
    f.mean_agreement = (sum(p.agreement for p in read) / len(read)
                        if read else 100.0)
    low = sum(p.low_conf for p in read)
    f.low_conf_share = 100.0 * low / f.tokens if f.tokens else 0.0
    f.failed = sorted(p.page for p in pages if p.error)
    for p in pages:
        f.per_page.append((p.page, round(p.agreement, 1), p.total))
        f.missed.extend((p.page, t) for t in p.missed)
        f.repairs.extend(p.repairs)
        f.disagreements.extend(w for w in p.words if w.get("needs_review"))
    return f


def scanned_pages(pdf_path: str) -> tuple[int, list[int]]:
    """``(page count, 1-based pages with no usable text layer)``."""
    import warnings

    import pdfplumber

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pdfplumber.open(pdf_path) as pdf:
            # EXACTLY the gate the PIPELINE applies (pagemodel.build_page_model):
            # the page's content is an image.  These two must never drift apart
            # -- a fidelity score computed over a different page set than the
            # one actually shipped is a verdict about a different document.
            #
            # Text volume was wrong here in both directions.  Requiring LITTLE
            # text fired on legitimately sparse text-layer pages, so eleven
            # "mixed" editions got agreement verdicts computed from 25-88 tokens
            # of REAL text (Customs 2008 pages 23/71/198/241 carry 139/76/160/24
            # chars and zero images) -- a verdict about nothing.  And it also
            # SKIPPED the pages that matter most: a full-page scan whose
            # embedded OCR layer is long but wrong sails over any char-count
            # threshold, which is how the three Finance (Supplementary) Acts
            # were never measured at all.  _page_is_scan alone decides.
            from .pagemodel import _page_is_scan
            return len(pdf.pages), [i for i, pg in enumerate(pdf.pages, 1)
                                    if _page_is_scan(pg)]


def _page_job(args) -> PageOCR:
    """One page, as a picklable unit of work for a process pool.

    A page that raises comes back carrying ``error`` rather than looking like
    an empty page -- an unreadable page must fail the file, not pass as blank.
    """
    pdf_path, pageno, dpi = args
    try:
        return ocr_page(pdf_path, pageno, dpi)
    except Exception as exc:
        return PageOCR(page=pageno, words=[], error=f"{type(exc).__name__}: {exc}")


def page_fidelity(pdf_path: str, pages: list[int] | None = None,
                  dpi: int = DEFAULT_DPI, mapper=map) -> Fidelity:
    """OCR every page of ``pdf_path`` that needs it and score the whole file.

    ``pages`` defaults to every page the trigger flags, which is what makes
    this the "over ALL pages, never a sample" path.  ``mapper`` lets a caller
    hand in ``ProcessPoolExecutor.map`` for parallelism without this module
    owning a pool.
    """
    if pages is None:
        pages = scanned_pages(pdf_path)[1]
    jobs = [(pdf_path, n, dpi) for n in pages]
    return fidelity_of(pdf_path, list(mapper(_page_job, jobs)))


# --------------------------------------------------------------------------
# self-check
# --------------------------------------------------------------------------

def _tw(text, box, conf=95.0, line=0, size=52.0):
    return {"text": text, "box": box, "conf": conf, "size_px": size,
            "line": line}


def _rl(text, box, conf=90.0):
    return {"text": text, "box": box, "conf": conf}


def _demo() -> None:
    # ---- px -> pt scaling ------------------------------------------------
    r = align([_tw("Act", (300, 600, 450, 650), size=52.0)],
              [_rl("Act", (300, 600, 450, 650))], pageno=7, dpi=300)
    w = r.words[0]
    assert (w["x0"], w["top"], w["x1"], w["bottom"]) == (72.0, 144.0, 108.0, 156.0), w
    assert w["size"] == 12.5, w["size"]          # 52 px @300dpi -> 12.5 pt
    assert w["fontname"] is None and w["conf"] == "agreed"
    assert w["needs_review"] is False and w["page"] == 7
    assert r.agreement == 100.0
    assert w["_space_before"] is True                    # first word of a line
    # size never comes back None even when hOCR gave no x_size
    r = align([_tw("Act", (300, 600, 450, 650), size=None)], [], dpi=300)
    assert r.words[0]["size"] == 16.7, r.words[0]["size"]

    # Every recognised token is its own word, however tight its box: hOCR splits
    # on whitespace, so a narrow gap is kerning and not a missing space.  The old
    # geometric test (gap >= 0.25 * size) glued Benami 2017's cover into
    # "provideforprohibitiont ofholdingpraperty" -- gaps of 0.72-1.44 pt at size
    # 10.6.  A scan must never have a jammed word invented for it.
    r = align([_tw("no", (100, 600, 150, 640), size=48.0),
               _tw("gap", (151, 600, 200, 640), size=48.0),
               _tw("wide", (260, 600, 320, 640), size=48.0)],
              [_rl("no gap wide", (100, 598, 320, 642))])
    assert [w["_space_before"] for w in r.words] == [True, True, True], \
        [(w["text"], w["_space_before"]) for w in r.words]

    # ---- agreement, disagreement, higher-confidence wins ----------------
    tess = [_tw("published", (100, 100, 300, 140), conf=90.0),
            _tw("ariificial", (310, 100, 500, 140), conf=5.0),
            _tw("firm,", (510, 100, 600, 140), conf=99.0)]
    rapid = [_rl("published artificial", (100, 98, 500, 142), conf=88.0),
             _rl("frm.", (510, 98, 600, 142), conf=40.0)]
    r = align(tess, rapid, pageno=4)
    got = {w["text"]: (w["conf"], w["needs_review"]) for w in r.words}
    assert got["published"] == ("agreed", False), got
    # RapidOCR was right and more confident -> its reading is accepted, still flagged
    assert got["artificial"] == (88.0, True), got
    # Tesseract more confident -> its reading kept, still flagged
    assert got["firm,"] == (99.0, True), got
    assert r.agreed == 1 and r.total == 3
    d = [w for w in r.words if w["text"] == "artificial"][0]
    assert d["tesseract"] == "ariificial" and d["rapidocr"] == "artificial", d

    # a line only RapidOCR saw counts against the page but yields no word
    r = align([_tw("A", (10, 10, 20, 20))], [_rl("A", (10, 10, 20, 20)),
                                             _rl("lost two", (10, 900, 400, 950))])
    assert len(r.words) == 1 and r.total == 3 and r.agreed == 1, (r.total, r.agreed)
    assert r.missed == ["lost two"]

    # multi-box RapidOCR line, marker box detected separately and to the left
    tess = [_tw("(b}", (400, 600, 520, 650), conf=72.0),
            _tw("amernber", (600, 600, 800, 650), conf=1.0),
            _tw("of", (810, 600, 860, 650)),
            _tw("persons;", (870, 600, 1000, 650))]
    rapid = [_rl("a nember of persons,", (600, 598, 1000, 652)),
             _rl("(b)", (398, 598, 522, 652))]
    r = align(tess, rapid, pageno=9)
    assert [w["needs_review"] for w in r.words] == [True, True, False, True], \
        [(w["text"], w["needs_review"]) for w in r.words]

    # ---- enumerator repair ---------------------------------------------
    def col(*items, x0=60.0, page=3, top0=100.0):
        """A column of markers: (text, conf) or (text, conf, rapid reading).

        Each marker is the leftmost token of its own printed line, which is
        what :func:`_line_leading` requires of a structural enumerator.
        """
        out = []
        for k, item in enumerate(items):
            text, conf = item[0], item[1]
            top = top0 + 20 * k
            out.append({"text": text, "x0": x0, "x1": x0 + 20, "top": top,
                        "bottom": top + 12, "size": 12.0, "fontname": None,
                        "conf": conf, "needs_review": conf != "agreed",
                        "page": page, "tesseract": text,
                        "rapidocr": item[2] if len(item) > 2 else None})
        return out

    ws, rep = repair_enumerators(col(("(a)", "agreed"), ("{b}", 41.0),
                                     ("(c)", "agreed"), ("(dl]", 21.0),
                                     ("[et]", 30.0)))
    assert [w["text"] for w in ws] == ["(a)", "(b)", "(c)", "(d)", "(e)"], \
        [w["text"] for w in ws]
    assert len(rep) == 3 and rep[0]["before"] == "{b}" and rep[0]["after"] == "(b)"
    # "{b}" still reads as b (shape fix); "(dl]" and "[et]" do not parse at
    # all, so only those two need the sequence
    assert [r["kind"] for r in rep] == ["shape", "sequence", "sequence"], rep
    assert all(w["needs_review"] for w in ws if "repair" in w), "repairs stay flagged"
    assert ws[1]["repair"] == "{b}"

    # a mangled FIRST marker is derived backwards from the next clean anchor
    ws, rep = repair_enumerators(col(("(al", 63.0), ("(b)", "agreed"),
                                     ("(c)", "agreed")))
    assert [w["text"] for w in ws] == ["(a)", "(b)", "(c)"], [w["text"] for w in ws]

    # roman column, and the two columns must not be mixed
    ws, rep = repair_enumerators(
        col(("(i)", "agreed"), ("(ii)", "agreed"), ("(iiil", 44.0))
        + col(("(a)", "agreed"), ("{b)", 30.0), ("(c)", "agreed"),
              x0=200.0, top0=400.0))
    assert [w["text"] for w in ws] == ["(i)", "(ii)", "(iii)",
                                       "(a)", "(b)", "(c)"], \
        [w["text"] for w in ws]

    # ---- what must NEVER be rewritten ----------------------------------
    # a digit-with-suffix cross reference: 99A misread as 994A stays as read
    ws, rep = repair_enumerators(col(("(a)", "agreed"), ("994A", 20.0),
                                     ("(c)", "agreed"), ("(d)", "agreed")))
    assert [w["text"] for w in ws] == ["(a)", "994A", "(c)", "(d)"], \
        [w["text"] for w in ws]
    assert rep == []
    assert _marker_core("994A") is None and _marker_core("99A") is None
    # a YEAR in brackets is marker-shaped and could sit in a marker column;
    # the sequence must never hand it a clause number
    ws, rep = repair_enumerators(col(("(1)", "agreed"), ("(2)", "agreed"),
                                     ("(2Ol8),", 30.0)))
    assert [w["text"] for w in ws] == ["(1)", "(2)", "(2Ol8),"] and rep == [], \
        ([w["text"] for w in ws], rep)
    # a marker-shaped token in RUNNING TEXT is not a structural enumerator:
    # "clauses (a) to (dl)." -- only a line's leftmost token may be repaired
    inline = col(("(a)", "agreed"), ("(b)", "agreed"), ("(c)", "agreed"))
    inline += [dict(inline[0], text="(dl)", x0=300.0, x1=320.0,
                    top=inline[2]["top"], bottom=inline[2]["bottom"],
                    conf=20.0, needs_review=True, tesseract="(dl)")]
    ws, rep = repair_enumerators(inline)
    assert [w["text"] for w in ws] == ["(a)", "(b)", "(c)", "(dl)"] and rep == [], \
        ([w["text"] for w in ws], rep)
    # a bracketed number is a marker shape but a clean one -> untouched
    ws, rep = repair_enumerators(col(("(1)", "agreed"), ("(2)", "agreed"),
                                     ("(7)", 30.0)))
    assert [w["text"] for w in ws] == ["(1)", "(2)", "(7)"], [w["text"] for w in ws]
    assert rep == []
    # A well-formed marker from ANOTHER alphabet is still well-formed: the
    # source prints it.  RTI 2017 p12/p2 once turned "(b)" into "(5)" and
    # "(ii)" into "(5)" because neither is a member of the numeric run.
    ws, rep = repair_enumerators(col(("(1)", "agreed"), ("(2)", "agreed"),
                                     ("(3)", "agreed"), ("(b)", 90.0),
                                     ("(ii)", 67.0), ("(aa)", 40.0)))
    assert [w["text"] for w in ws] == ["(1)", "(2)", "(3)",
                                       "(b)", "(ii)", "(aa)"], \
        [w["text"] for w in ws]
    assert rep == []
    # "(0)" after "(g) (h)" is almost certainly a misread "(i)" -- and is still
    # left alone, because the shape is well-formed and this pass does not
    # second-guess a marker the engines rendered cleanly.  It stays flagged.
    ws, rep = repair_enumerators(col(("(g)", "agreed"), ("(h)", "agreed"),
                                     ("(0)", 59.0)))
    assert [w["text"] for w in ws] == ["(g)", "(h)", "(0)"] and rep == [], \
        ([w["text"] for w in ws], rep)
    assert ws[2]["needs_review"] is True
    # a body word both engines agreed on is never a candidate, bracketed or not
    ws, rep = repair_enumerators(col(("(a)", "agreed"), ("(the", "agreed"),
                                     ("(c)", "agreed")))
    assert [w["text"] for w in ws] == ["(a)", "(the", "(c)"] and rep == []
    # ... nor is a low-confidence body word: too long to be a marker
    ws, rep = repair_enumerators(col(("(a)", "agreed"), ("(income", 12.0),
                                     ("(c)", "agreed")))
    assert [w["text"] for w in ws] == ["(a)", "(income", "(c)"] and rep == []
    # a single clean anchor is not enough to fix a neighbour
    ws, rep = repair_enumerators(col(("(a)", "agreed"), ("{x}", 20.0)))
    assert rep == [] and ws[1]["text"] == "{x}"
    # A confident-but-flagged marker is NOT an anchor.  Recorded from Benami
    # 2017 p4: the source prints (a)(b)(c)(d)(e); Tesseract read
    # (zt)/{b)/(c}/{dJ/je] and RapidOCR read [a]/(b)/(e)/(a)/[e], so the
    # accepted column is a,b,e,a,? -- anchoring on those "clean" (e)/(a) once
    # rewrote the final (e) to (b).  Nothing in this column may be repaired.
    ws, rep = repair_enumerators(col(("(zt)", 68.0), ("(b)", 67.5),
                                     ("(e)", 61.7), ("(a)", 64.9),
                                     ("je]", 72.0)))
    assert [w["text"] for w in ws] == ["(zt)", "(b)", "(e)", "(a)", "je]"], \
        [w["text"] for w in ws]
    assert rep == []

    # a restart (a),(b),(a),(b) must not be read as a run of four
    ws, rep = repair_enumerators(col(("(a)", "agreed"), ("(b)", "agreed"),
                                     ("(a)", "agreed"), ("{b|", 30.0)))
    assert [w["text"] for w in ws] == ["(a)", "(b)", "(a)", "(b)"], \
        [w["text"] for w in ws]
    # "{b|" still parses as b, so it is a shape fix, not a sequence guess
    assert [r["kind"] for r in rep] == ["shape"], rep

    # The sequence may NOT override a value both engines read.  Benami 2017
    # p14, column x0~110: (2) (3) (4).. (5) | (2) (3): {2]  -- the final "{2]"
    # is a new section's subsection 2, which both engines read as 2, but it
    # sits at sequence position 4 and was once rewritten to "(4)".
    ws, rep = repair_enumerators(col(("(2)", "agreed"), ("(3)", 96.0, "(3]"),
                                     ("(4}", 87.1, "(4).."), ("(5)", "agreed"),
                                     ("(2)", "agreed"), ("(3)", 91.1, "(3):"),
                                     ("{2]", 82.0, "[2]")))
    assert [w["text"] for w in ws] == ["(2)", "(3)", "(4)", "(5)",
                                       "(2)", "(3)", "(2)"], \
        [w["text"] for w in ws]
    assert {r["kind"] for r in rep} == {"shape"}, rep
    # ... and when the engines read two *different* values, nothing is chosen
    ws, rep = repair_enumerators(col(("(a)", "agreed"), ("(b)", "agreed"),
                                     ("(c}", 36.0, "(e)")))
    assert [w["text"] for w in ws] == ["(a)", "(b)", "(c}"], \
        [w["text"] for w in ws]
    assert rep == []

    # ---- fidelity floor arithmetic --------------------------------------
    p1 = PageOCR(page=1, words=[], agreed=90, total=100, low_conf=5)
    p2 = PageOCR(page=2, words=[], agreed=80, total=100, low_conf=25)
    f = fidelity_of("x.pdf", [p1, p2])
    assert f.mean_agreement == 85.0 and f.low_conf_share == 15.0
    assert f.admitted, f.reason                        # exactly on the floor
    p2.agreed = 79
    f = fidelity_of("x.pdf", [p1, p2])
    assert not f.admitted and "mean agreement 84.5%" in f.reason, f.reason
    p2.agreed, p2.low_conf = 80, 26
    f = fidelity_of("x.pdf", [p1, p2])
    assert not f.admitted and "low-confidence tokens 15.5%" in f.reason, f.reason
    # a clean sample cannot rescue a rotten file: the mean is over ALL pages
    f = fidelity_of("x.pdf", [PageOCR(page=i, words=[], agreed=100, total=100)
                              for i in range(1, 6)]
                    + [PageOCR(page=i, words=[], agreed=40, total=100)
                       for i in range(6, 41)])
    assert not f.admitted and f.pages == 40, (f.pages, f.mean_agreement)
    assert not fidelity_of("x.pdf", []).admitted
    # a page that ERRORED must not pass as a harmless blank page
    f = fidelity_of("x.pdf", [PageOCR(page=1, words=[], agreed=99, total=100),
                              PageOCR(page=2, words=[], error="RuntimeError: x")])
    assert not f.admitted and f.failed == [2], (f.failed, f.reason)
    assert "1 page(s) failed to OCR: 2" in f.reason, f.reason
    # a trailing blank page is not a fidelity failure
    f = fidelity_of("x.pdf", [PageOCR(page=1, words=[], agreed=99, total=100,
                                      low_conf=3),
                              PageOCR(page=2, words=[], agreed=0, total=0)])
    assert f.admitted and f.blank == 1 and f.mean_agreement == 99.0, f.reason

    print("acts_ingest.ocr: self-check OK")


if __name__ == "__main__":
    _demo()

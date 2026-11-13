"""Positioned words from a text-layer PDF (Phase 4AF, reader `pdf-words-3` after Phase 4AG review).

`extract_pdf` returns readable text per page, which loses the layout a table needs. This module keeps, for every word or
phrase, the page, the left and right edge, the baseline and the font size, so `table_grid` can read rows and columns
geometrically. Glyphs come from `pdfminer.six` one character at a time with their real positions and advances (the earlier
`pypdf` visitor returned everything drawn in one `BT..ET` block as one string, which hid every cell boundary of the way real
reports are written). The parser runs under the same hardened child-process rules as `extract_pdf` (hostile bytes,
wall-clock, CPU and memory limits, JSON only back). All text is untrusted data.

Words are assembled conservatively, because a wrong boundary is a wrong number:

* a glyph run is split at a space glyph, at a gap above 0.15 em, and wherever the baseline or the font size changes;
* two neighbouring pieces join into one phrase (a row label) only across a gap of at most 0.45 em, and **never when both
  are value-like**, so two figures are never read as one;
* a smaller piece touching the end of the previous one on a shifted baseline (a footnote marker) is kept, as a superscript
  character on that word (`3.25` and a raised `1` become `3.25¹`, never `3.251`), so the figure is later refused as footnoted;
* rotated text is dropped (a table read sideways is not read), and a glyph with no Unicode mapping stays visible as
  `(cid:N)` so its cell cannot parse as a number.
* recognised overprints are read once; unresolved glyph overlays refuse the whole PDF before word assembly.

Not detected (documented): invisible text (render mode 3), text clipped away, and white-on-white text.
"""

from __future__ import annotations

import dataclasses
import io
import json
import logging
import math
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from nzstats.domain import ErrorClass, IngestError
from nzstats.research.extract import ExtractionLimits, clean_text
from nzstats.research.extract_pdf import (
    PDF_TIMEOUT_SECONDS,
    _apply_child_limits,
    _child_env,
    _limit_error,
)

log = logging.getLogger(__name__)
EXTRACTOR_VERSION = "pdf-words-3"
_MAX_WORDS = 200_000
_MAX_CHARS = 1_000_000
_MAX_PAGE_CONTENT = 300_000  # bytes of one page's decompressed content stream; refused before layout (macOS has no address-space limit)

# Gap constants are the implementer's calls, each covered by boundary tests.
_TOKEN_GAP = 0.15  # em: a larger gap between glyphs ends a token (kerning is far smaller)
_DIGIT_GAP = 0.03  # em: between two figure characters even a small gap ends the token (two cells, not one number)
_FIGURE_CHARS = frozenset("0123456789.,%-\u2212\u2013")
_PHRASE_GAP = 0.45  # em: a larger gap between tokens separates cells
_MARKER_GAP = (
    0.35  # em: a smaller shifted piece this close to the previous one is a footnote marker
)
_SHIFT = 0.15  # em: baseline movement that starts a new token
_SIZE_RATIO = 0.85  # a font size ratio below this (or above its inverse) starts a new token
_BASE_BREAK = 0.45  # em: baselines further apart than this are different lines
_SUPERSCRIPT = str.maketrans(
    "0123456789", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"
)
_VALUE_LIKE = re.compile(
    r"^(?:[-\u2212\u2013(]?\d[\d,.]*%?\)?[*\u2020\u2021\u00b9\u00b2\u00b3\u2074-\u2079]*|[-\u2013\u2014]|n/?a|\.{2,})$",
    re.IGNORECASE,
)
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
# A whole period header: "Mar-26", "Dec 2026", "Q3 2026", "2027", "FY27", "2026/27".
_PERIOD_LIKE = re.compile(
    rf"^(?:{_MONTH}[-/ ]?\d{{2,4}}|q[1-4][-/ ]?\d{{2,4}}|(?:fy|cy)?\d{{4}}(?:[-/]\d{{2,4}})?[a-z]?|(?:fy|cy)\d{{2}})$",
    re.IGNORECASE,
)
_MONTH_ONLY = re.compile(rf"^(?:{_MONTH}|q[1-4])$", re.IGNORECASE)
_PERIOD_START = re.compile(rf"^(?:{_MONTH}|q[1-4]|year|fy|cy|\d)", re.IGNORECASE)


def cell_boundary(left: str, right: str) -> bool:
    """Whether two neighbouring pieces of text are two cells that must never be read as one phrase.

    Two value-like pieces (figures, dashes) are two cells. So are two whole period headers, and a header that ends in a year
    followed by the start of another period ("Dec 2026" then "Mar 2027"). A month or quarter followed by its own year
    ("Dec", then "2026") is one header.
    """
    last = left.rsplit(" ", 1)[-1]
    if _VALUE_LIKE.match(last) and _VALUE_LIKE.match(right):
        return True
    if _PERIOD_LIKE.match(last) and _PERIOD_LIKE.match(right):
        return True
    if _MONTH_ONLY.match(last) and _MONTH_ONLY.match(right):
        return True  # "Dec" then "Mar": two headers (a month then its own year is one header, handled above)
    return bool(_PERIOD_LIKE.match(last) and _PERIOD_START.match(right) and re.search(r"\d", last))


@dataclasses.dataclass(frozen=True)
class Word:
    page: int
    x0: float
    x1: float
    y: float  # baseline, points from the bottom of the page
    size: float
    text: str


def extract_words(
    body: bytes,
    limits: ExtractionLimits | None = None,
    *,
    isolate: bool | None = None,
    timeout: float = PDF_TIMEOUT_SECONDS,
) -> tuple[Word, ...]:
    limits = limits or ExtractionLimits()
    if len(body) > limits.max_pdf_bytes:
        raise IngestError(ErrorClass.VALIDATION_FAILED, "pdf too large")
    if b"%PDF-" not in body[:1024]:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "not a pdf (no %PDF- header)")
    if isolate if isolate is not None else True:
        return _extract_isolated(body, limits, timeout)
    return _extract(body, limits)


@dataclasses.dataclass(frozen=True)
class _Glyph:
    page: int
    x0: float
    x1: float
    base: float  # baseline of the text matrix (the text-rise operator is not included)
    y0: float  # bottom of the glyph box: baseline, descent and text rise together
    size: float
    font: str
    text: str


@dataclasses.dataclass
class _Token:
    text: str
    x0: float
    x1: float
    base: float
    size: float
    shifted: bool  # starts where the baseline or the font size changed


def _finite(*values: float) -> bool:
    return all(math.isfinite(v) for v in values)


def _walk(node, depth: int = 0):
    """Characters of a pdfminer layout node, in drawing order (Form XObjects nest, bounded by depth)."""
    from pdfminer.layout import LTChar

    if isinstance(node, LTChar):
        yield node
    elif depth < 8 and hasattr(node, "__iter__"):
        for child in node:
            yield from _walk(child, depth + 1)


def _page_glyphs(number: int, layout, counter: list[int]) -> tuple[list[_Glyph], int]:
    """Upright glyphs of one page and how many rotated ones were left out."""
    found: list[_Glyph] = []
    rotated = 0
    for ch in _walk(layout):
        counter[0] += 1
        if counter[0] > _MAX_CHARS:
            raise IngestError(ErrorClass.VALIDATION_FAILED, "pdf_extraction_limit (characters)")
        text = ch.get_text() or ""
        if not ch.upright:
            rotated += 1
            continue
        base = ch.matrix[5]
        if not _finite(ch.x0, ch.x1, base, ch.y0, ch.size):
            continue
        found.append(_Glyph(number, ch.x0, ch.x1, base, ch.y0, abs(ch.size), ch.fontname, text))
    glyphs = _without_overprints(found)
    _reject_overlaps(glyphs)
    return glyphs, rotated


def _without_overprints(glyphs: list[_Glyph]) -> list[_Glyph]:
    """Drop a glyph drawn again almost on top of the same glyph (fake bold, drop shadows).

    "Almost" is geometric, not a rounding bucket: the same character, the same size, within a tenth of an em vertically and
    less than half its own width horizontally. A real repeated character advances by a whole glyph width, so it is never
    dropped; an overprint that moves by more than half a glyph is not recognised and the residual-overlap check refuses it.
    """
    by_text: dict[str, list[_Glyph]] = {}
    for g in glyphs:
        by_text.setdefault(g.text, []).append(g)
    kept: list[_Glyph] = []
    for group in by_text.values():
        group.sort(key=lambda g: (g.x0, g.base))
        recent: list[_Glyph] = []
        for g in group:
            near = (
                k
                for k in reversed(recent)
                if g.x0 - k.x0 < 0.5 * max(k.x1 - k.x0, 1e-6)
                and abs(g.base - k.base) <= 0.1 * g.size
                and abs(g.y0 - k.y0) <= 0.1 * g.size
                and abs(g.size - k.size) <= 0.05 * g.size
            )
            if next(near, None) is None:
                recent.append(g)
                kept.append(g)
            while recent and g.x0 - recent[0].x0 >= max(recent[0].x1 - recent[0].x0, 1.0):
                recent.pop(0)
    return kept


def _reject_overlaps(glyphs: list[_Glyph]) -> None:
    """Refuse unresolved overlays before line grouping can hide their geometry.

    Recognised overprints have already been removed. Figures permit only the same small kerning allowance used for
    numeric gaps, capped by half the narrower advance even under horizontal scaling; ordinary text permits kerning below
    half the narrower advance. Use the visible vertical interval,
    including text rise, independently of the baseline tolerances used to assemble lines and tokens.
    """
    recent: list[_Glyph] = []
    for g in sorted((g for g in glyphs if g.text.strip()), key=lambda g: g.x0):
        recent = [k for k in recent if k.x1 > g.x0]
        for k in recent:
            if k.page != g.page or min(k.y0 + k.size, g.y0 + g.size) <= max(k.y0, g.y0):
                continue
            overlap = min(k.x1, g.x1) - g.x0
            figures = k.text in _FIGURE_CHARS and g.text in _FIGURE_CHARS
            allowance = 0.5 * min(k.x1 - k.x0, g.x1 - g.x0)
            if figures:
                allowance = min(allowance, _DIGIT_GAP * min(k.size, g.size))
            if overlap > allowance:
                raise IngestError(ErrorClass.LAYOUT_CHANGED, "ambiguous_glyph_overlap")
        recent.append(g)


def _lines(glyphs: list[_Glyph]) -> list[list[_Glyph]]:
    """Glyphs grouped by baseline. A raised marker (a smaller shifted baseline) stays in its line."""
    ordered = sorted(glyphs, key=lambda g: (-g.base, g.x0))
    lines: list[list[_Glyph]] = []
    last: _Glyph | None = None
    for g in ordered:
        if last is not None and last.base - g.base <= _BASE_BREAK * max(last.size, g.size):
            lines[-1].append(g)
        else:
            lines.append([g])
        last = g
    return lines


def _tokens(line: list[_Glyph]) -> list[_Token]:
    tokens: list[_Token] = []
    current: list[_Glyph] = []
    prev: _Glyph | None = None  # the previous non-blank glyph
    blank_before = False

    def close() -> None:
        nonlocal current
        if current:
            text = " ".join(clean_text("".join(g.text for g in current)).split())
            if text:
                first, last = current[0], current[-1]
                tokens.append(_Token(text, first.x0, last.x1, first.base, first.size, False))
        current = []

    for g in sorted(line, key=lambda g: g.x0):
        if not g.text.strip():
            close()
            blank_before = True
            continue
        if prev is not None and current:
            ratio = g.size / prev.size if prev.size else 1.0
            moved = abs(g.base - prev.base) > _SHIFT * prev.size or (
                g.font == prev.font and abs(g.y0 - prev.y0) > _SHIFT * prev.size
            )
            resized = ratio < _SIZE_RATIO or ratio > 1 / _SIZE_RATIO
            figures = g.text in _FIGURE_CHARS and prev.text in _FIGURE_CHARS
            limit = _DIGIT_GAP if figures else _TOKEN_GAP
            if blank_before or g.x0 - prev.x1 > limit * prev.size or moved or resized:
                close()
        current.append(g)
        prev, blank_before = g, False
    close()
    for before, after in zip(tokens, tokens[1:], strict=False):
        ratio = after.size / before.size if before.size else 1.0
        after.shifted = (
            abs(after.base - before.base) > _SHIFT * before.size
            or ratio < _SIZE_RATIO
            or ratio > 1 / _SIZE_RATIO
        )
    return tokens


def _words_of(number: int, tokens: list[_Token]) -> list[Word]:
    words: list[Word] = []
    cur: _Token | None = None
    for tok in tokens:
        if cur is None:
            cur = dataclasses.replace(tok)
            continue
        gap = tok.x0 - cur.x1
        if tok.shifted and tok.size < _SIZE_RATIO * cur.size and gap < _MARKER_GAP * cur.size:
            cur.text += tok.text.translate(
                _SUPERSCRIPT
            )  # a footnote marker stays on its figure, visibly
            cur.x1 = tok.x1
        elif tok.shifted or gap > _PHRASE_GAP * cur.size or cell_boundary(cur.text, tok.text):
            words.append(Word(number, cur.x0, cur.x1, cur.base, cur.size, cur.text))
            cur = dataclasses.replace(tok)
        else:
            cur.text += " " + tok.text
            cur.x1 = tok.x1
    if cur is not None:
        words.append(Word(number, cur.x0, cur.x1, cur.base, cur.size, cur.text))
    return words


def _extract(body: bytes, limits: ExtractionLimits) -> tuple[Word, ...]:
    try:
        from pdfminer.high_level import extract_pages
        from pypdf import PdfReader
    except ImportError:
        raise IngestError(ErrorClass.UNEXPECTED, "pdf_support_not_installed") from None
    words: list[Word] = []
    rotated = 0
    counter = [0]
    try:
        reader = PdfReader(io.BytesIO(body), strict=False)
        if reader.is_encrypted:
            raise IngestError(ErrorClass.BLOCKED, "pdf is encrypted")
        pages = len(reader.pages)
        if pages == 0:
            raise IngestError(ErrorClass.LAYOUT_CHANGED, "unreadable pdf (no pages)")
        if pages > limits.max_pages:
            raise IngestError(ErrorClass.VALIDATION_FAILED, f"pdf has too many pages ({pages})")
        for page in reader.pages:
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > _MAX_PAGE_CONTENT:
                raise IngestError(ErrorClass.VALIDATION_FAILED, "pdf_extraction_limit (content)")
        for number, layout in enumerate(
            extract_pages(
                io.BytesIO(body), laparams=None, maxpages=limits.max_pages, caching=False
            ),
            start=1,
        ):
            glyphs, turned = _page_glyphs(number, layout, counter)
            rotated += turned
            for line in _lines(glyphs):
                for word in _words_of(number, _tokens(line)):
                    if len(words) >= _MAX_WORDS:
                        raise IngestError(
                            ErrorClass.VALIDATION_FAILED, "pdf_extraction_limit (words)"
                        )
                    words.append(word)
    except IngestError:
        raise
    except Exception as exc:  # parsers raise many types on damaged input: keep only the type
        log.warning("pdf word extraction failed: %r", exc)
        raise IngestError(
            ErrorClass.LAYOUT_CHANGED, f"unreadable pdf ({type(exc).__name__})"
        ) from None
    if not words:
        raise IngestError(
            ErrorClass.VALIDATION_FAILED, "rotated_text_only" if rotated else "no_text_layer"
        )
    return tuple(sorted(words, key=lambda w: (w.page, -w.y, w.x0)))


def _reply_cap() -> int:
    return 64 * _MAX_WORDS + 1024 * 1024


def _extract_isolated(body: bytes, limits: ExtractionLimits, timeout: float) -> tuple[Word, ...]:
    # `-I` ignores PYTHONPATH, so the child is told which source tree to load: the one this process runs from.
    root = str(Path(__file__).resolve().parents[2])
    command = [
        sys.executable, "-I", "-c", _CHILD_SNIPPET, root, json.dumps(dataclasses.asdict(limits)),
    ]  # fmt: skip
    with tempfile.TemporaryFile() as out:
        try:
            done = subprocess.run(
                command, input=body, stdout=out, stderr=subprocess.DEVNULL, timeout=timeout,
                check=False, env=_child_env(),
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            raise _limit_error() from None
        if out.seek(0, 2) > _reply_cap():
            raise _limit_error()
        out.seek(0)
        raw = out.read()
    try:
        reply = json.loads(raw)
    except ValueError:
        log.warning("pdf words child exited %s without a result", done.returncode)
        raise _limit_error() from None
    if "error" in reply:
        error_class, message = reply["error"]
        raise IngestError(ErrorClass(error_class), str(message))
    return tuple(Word(*w) for w in reply["ok"])


def words_sha256(words: Sequence[Word]) -> str:
    """Change-detection key over the positioned words (coordinates rounded to 0.1 point)."""
    import hashlib

    canonical = "\n".join(
        f"{w.page}|{w.x0:.1f}|{w.x1:.1f}|{w.y:.1f}|{w.size:.1f}|{w.text}" for w in words
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


_CHILD_SNIPPET = (
    "import sys; r = sys.argv[1];"
    " sys.path.insert(0, r) if 'site-packages' not in r else None; sys.argv[1:] = sys.argv[2:];"
    " from nzstats.research.table_words import _child_main; raise SystemExit(_child_main())"
)


def _child_main() -> int:
    limits = ExtractionLimits(**json.loads(sys.argv[1]))
    _apply_child_limits(limits)
    try:
        result = {"ok": [dataclasses.astuple(w) for w in _extract(sys.stdin.buffer.read(), limits)]}
    except IngestError as exc:
        result = {"error": [exc.error_class.value, str(exc)]}
    except MemoryError:
        result = {"error": [ErrorClass.VALIDATION_FAILED.value, str(_limit_error())]}
    sys.stdout.write(json.dumps(result))
    return 0

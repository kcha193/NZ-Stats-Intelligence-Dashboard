"""Positioned words from a text-layer PDF (Phase 4AF): where each piece of text sits on its page.

`extract_pdf` returns readable text per page, which loses the layout a table needs. This module keeps, for every
text-showing operation, the page, the left and right edge, the baseline and the font size, so `table_grid` can read
rows and columns geometrically. The parser runs under the same hardened child-process rules as `extract_pdf` (hostile
bytes, wall-clock, CPU and memory limits, JSON only back). All text is untrusted data.

The right edge is estimated from the text and the font size (no font file is read) with Helvetica-like advances, so it
is approximate: it is used only to decide which column a cell overlaps, never to change a value.
"""

from __future__ import annotations

import dataclasses
import io
import json
import logging
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
EXTRACTOR_VERSION = "pdf-words-1"
_MAX_WORDS = 200_000

_NARROW = frozenset(".,:;'|!iIl ")
_DIGIT_ADVANCE, _NARROW_ADVANCE, _OTHER_ADVANCE = 0.556, 0.278, 0.55


@dataclasses.dataclass(frozen=True)
class Word:
    page: int
    x0: float
    x1: float
    y: float  # baseline, points from the bottom of the page
    size: float
    text: str


def _advance(ch: str) -> float:
    if ch.isdigit():
        return _DIGIT_ADVANCE
    if ch in "-−–—":
        return 0.333
    return _NARROW_ADVANCE if ch in _NARROW else _OTHER_ADVANCE


def text_width(text: str, size: float) -> float:
    return sum(_advance(c) for c in text) * size


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


def _extract(body: bytes, limits: ExtractionLimits) -> tuple[Word, ...]:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise IngestError(ErrorClass.UNEXPECTED, "pdf_support_not_installed") from None
    words: list[Word] = []
    try:
        reader = PdfReader(io.BytesIO(body), strict=False)
        if reader.is_encrypted:
            raise IngestError(ErrorClass.BLOCKED, "pdf is encrypted")
        pages = len(reader.pages)
        if pages == 0:
            raise IngestError(ErrorClass.LAYOUT_CHANGED, "unreadable pdf (no pages)")
        if pages > limits.max_pages:
            raise IngestError(ErrorClass.VALIDATION_FAILED, f"pdf has too many pages ({pages})")
        for number, page in enumerate(reader.pages, start=1):

            def visit(text, cm, tm, _font, font_size, number=number):
                text = " ".join(clean_text(text or "").split())
                if not text:
                    return
                if len(words) >= _MAX_WORDS:
                    raise IngestError(ErrorClass.VALIDATION_FAILED, "pdf_extraction_limit (words)")
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                size = abs(font_size * tm[3] * cm[3]) or abs(font_size)
                words.append(Word(number, x, x + text_width(text, size), y, size, text))

            page.extract_text(visitor_text=visit)
    except IngestError:
        raise
    except Exception as exc:  # pypdf raises many types on damaged input: keep only the type
        log.warning("pdf word extraction failed: %r", exc)
        raise IngestError(
            ErrorClass.LAYOUT_CHANGED, f"unreadable pdf ({type(exc).__name__})"
        ) from None
    if not words:
        raise IngestError(ErrorClass.VALIDATION_FAILED, "no_text_layer")
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
    "import sys; sys.path.insert(0, sys.argv[1]); sys.argv[1:] = sys.argv[2:];"
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

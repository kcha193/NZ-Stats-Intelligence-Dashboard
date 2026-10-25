"""Readable text from a public PDF report, one section per page (`pypdf`, an optional extra).

Sections are per page so that every evidence reference has an exact page number; heading detection
from PDF text is unreliable and is left to a later extractor version. PDF metadata dates are when a
file was made, not when it was published, so no date hint comes from here. Encrypted PDFs are treated
as access-restricted, never decrypted.

A PDF is a program-like format and the bytes are untrusted, so by default the parser runs in a
short-lived child process (`python -I -m nzstats.research.extract_pdf`) with a wall-clock timeout and,
where the OS supports them, CPU-time and address-space limits. A decompression bomb or a parser loop
then costs one child, not the scheduler process. Only JSON crosses back.
"""

from __future__ import annotations

import dataclasses
import io
import json
import logging
import subprocess
import sys
import tempfile
import warnings

from nzstats.domain import ErrorClass, IngestError
from nzstats.research.extract import (
    Extracted,
    ExtractionLimits,
    Section,
    build_sections,
    clean_text,
    too_long,
)

EXTRACTOR_VERSION = "pdf-1"
ISOLATE_DEFAULT = True
PDF_TIMEOUT_SECONDS = 60.0
CHILD_MEMORY_BYTES = 1024 * 1024 * 1024
CHILD_CPU_SECONDS = 60

log = logging.getLogger(__name__)


def extract_pdf(
    body: bytes,
    limits: ExtractionLimits,
    *,
    isolate: bool | None = None,
    timeout: float = PDF_TIMEOUT_SECONDS,
) -> Extracted:
    if len(body) > limits.max_pdf_bytes:
        raise IngestError(ErrorClass.VALIDATION_FAILED, "pdf too large")
    if b"%PDF-" not in body[:1024]:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "not a pdf (no %PDF- header)")
    if isolate if isolate is not None else ISOLATE_DEFAULT:
        return _extract_isolated(body, limits, timeout)
    return _extract(body, limits)


def _extract(body: bytes, limits: ExtractionLimits) -> Extracted:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise IngestError(ErrorClass.UNEXPECTED, "pdf_support_not_installed") from None
    try:
        reader = PdfReader(io.BytesIO(body), strict=False)
        if reader.is_encrypted:
            raise IngestError(ErrorClass.BLOCKED, "pdf is encrypted")
        page_count = len(reader.pages)
        if page_count == 0:
            raise IngestError(ErrorClass.LAYOUT_CHANGED, "unreadable pdf (no pages)")
        if page_count > limits.max_pages:
            raise IngestError(
                ErrorClass.VALIDATION_FAILED, f"pdf has too many pages ({page_count})"
            )
        blocks, total = [], 0
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            total += len(text)
            if total > 2 * limits.max_chars:  # bound memory before cleaning
                raise too_long(limits)
            blocks.append((None, text, number, number))
        title = _title(reader)
    except IngestError:
        raise
    # pypdf raises many exception types on damaged input: classify it and keep only the type.
    except Exception as exc:
        log.warning("pdf extraction failed: %r", exc)
        raise IngestError(
            ErrorClass.LAYOUT_CHANGED, f"unreadable pdf ({type(exc).__name__})"
        ) from None
    sections, warnings = build_sections(blocks, limits)
    if not sections:
        raise IngestError(ErrorClass.VALIDATION_FAILED, "no_text_layer")
    return Extracted(
        format="pdf",
        title=title,
        sections=sections,
        published_hint=None,
        extractor_version=EXTRACTOR_VERSION,
        page_count=page_count,
        warnings=warnings,
    )


def _title(reader) -> str | None:
    raw = reader.metadata.title if reader.metadata else None
    title = " ".join(clean_text(str(raw)).split()) if raw else ""
    return title[:300] or None


def _limit_error() -> IngestError:
    return IngestError(ErrorClass.VALIDATION_FAILED, "pdf_extraction_limit (time or memory)")


def _reply_cap(limits: ExtractionLimits) -> int:
    # JSON escapes a character to at most 6 bytes; headings and titles are small and capped.
    return 8 * limits.max_chars + 1024 * 1024


def _extract_isolated(body: bytes, limits: ExtractionLimits, timeout: float) -> Extracted:
    command = [sys.executable, "-I", "-m", __name__, json.dumps(dataclasses.asdict(limits))]
    # The reply goes to a file, not a pipe buffer, and stderr (parser warnings) is discarded, so a
    # hostile document cannot make this process buffer unbounded output.
    with tempfile.TemporaryFile() as out:
        try:
            done = subprocess.run(
                command, input=body, stdout=out, stderr=subprocess.DEVNULL, timeout=timeout,
                check=False,
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            raise _limit_error() from None
        size = out.seek(0, 2)
        if size > _reply_cap(limits):
            raise _limit_error()
        out.seek(0)
        raw = out.read()
    try:
        reply = json.loads(raw)
    except ValueError:
        log.warning("pdf child exited %s without a result", done.returncode)
        raise _limit_error() from None
    if "error" in reply:
        error_class, message = reply["error"]
        raise IngestError(ErrorClass(error_class), str(message))
    data = reply["ok"]
    data["sections"] = tuple(Section(**s) for s in data["sections"])
    data["warnings"] = tuple(data["warnings"])
    return Extracted(**data)


def _apply_child_limits(limits: ExtractionLimits) -> None:
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    try:
        import resource
    except ImportError:  # not POSIX: the parent's timeout still applies
        return
    for name, value in (
        ("RLIMIT_AS", CHILD_MEMORY_BYTES),
        ("RLIMIT_CPU", CHILD_CPU_SECONDS),
        ("RLIMIT_FSIZE", _reply_cap(limits)),  # bounds the reply file
    ):
        limit = getattr(resource, name, None)
        if limit is None:
            continue
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            pass  # e.g. macOS refuses RLIMIT_AS; the parent's timeout still applies


def _child_main() -> int:
    limits = ExtractionLimits(**json.loads(sys.argv[1]))
    _apply_child_limits(limits)
    try:
        result = {"ok": dataclasses.asdict(_extract(sys.stdin.buffer.read(), limits))}
    except IngestError as exc:
        result = {"error": [exc.error_class.value, str(exc)]}
    except MemoryError:
        result = {"error": [ErrorClass.VALIDATION_FAILED.value, str(_limit_error())]}
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_child_main())

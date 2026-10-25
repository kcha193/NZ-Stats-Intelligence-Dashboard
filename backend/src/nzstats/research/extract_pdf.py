"""Readable text from a public PDF report, one section per page (`pypdf`, an optional extra).

Sections are per page so that every evidence reference has an exact page number; heading detection
from PDF text is unreliable and is left to a later extractor version. PDF metadata dates are when a
file was made, not when it was published, so no date hint comes from here. Encrypted PDFs are treated
as access-restricted, never decrypted.
"""

from __future__ import annotations

import io
import logging

from nzstats.domain import ErrorClass, IngestError
from nzstats.research.extract import (
    Extracted,
    ExtractionLimits,
    build_sections,
    clean_text,
    too_long,
)

EXTRACTOR_VERSION = "pdf-1"

log = logging.getLogger(__name__)


def extract_pdf(body: bytes, limits: ExtractionLimits) -> Extracted:
    if len(body) > limits.max_pdf_bytes:
        raise IngestError(ErrorClass.VALIDATION_FAILED, "pdf too large")
    if b"%PDF-" not in body[:1024]:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "not a pdf (no %PDF- header)")
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

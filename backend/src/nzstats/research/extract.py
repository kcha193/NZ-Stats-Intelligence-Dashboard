"""What an extractor produces, the limits it works under, and text normalisation.

Extractors only parse: they turn bytes into a title, sections and a publication-date hint. Whether
the result may be stored is decided by `research.validate`. All extracted text is untrusted data; it is
never rendered, executed or followed as instructions.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from nzstats.domain import ErrorClass, IngestError

# Zero-width characters, bidi embeddings/overrides/isolates and the BOM: invisible, and used to hide
# or reorder text.
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿­]")
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_SPACES = re.compile(r"[^\S\n]+")
_BLANK_LINES = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class ExtractionLimits:
    max_html_bytes: int = 5 * 1024 * 1024
    max_pdf_bytes: int = 20 * 1024 * 1024
    max_pages: int = 300
    max_chars: int = 2_000_000
    max_sections: int = 400
    max_depth: int = 512
    max_heading_chars: int = 300


@dataclass(frozen=True)
class Section:
    ordinal: int
    heading: str | None
    text: str
    page_start: int | None = None
    page_end: int | None = None
    char_start: int = 0  # offsets into `Extracted.text`
    char_end: int = 0


@dataclass(frozen=True)
class Extracted:
    format: Literal["html", "pdf"]
    title: str | None
    sections: tuple[Section, ...]
    published_hint: str | None
    extractor_version: str
    page_count: int | None = None
    warnings: tuple[str, ...] = ()
    untrusted: bool = True  # always: Phase 3B must frame this as quoted data, never as instructions

    @property
    def text(self) -> str:
        return SEPARATOR.join(s.text for s in self.sections)

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.sections)

    @property
    def text_sha256(self) -> str:
        """Change-detection key: headings and text with whitespace collapsed."""
        canonical = "\n".join(
            " ".join(f"{s.heading or ''}\n{s.text}".split()) for s in self.sections
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


SEPARATOR = "\n\n"


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = _INVISIBLE.sub("", text)
    text = _CONTROL.sub(" ", text.replace("\t", " "))
    lines = (_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def too_long(limits: ExtractionLimits) -> IngestError:
    return IngestError(
        ErrorClass.VALIDATION_FAILED, f"extracted text too long (> {limits.max_chars})"
    )


def build_sections(
    blocks: Iterable[tuple[str | None, str, int | None, int | None]], limits: ExtractionLimits
) -> tuple[tuple[Section, ...], tuple[str, ...]]:
    """(heading, text, page_start, page_end) blocks -> numbered sections with offsets.

    Empty blocks are dropped; past `max_sections` the remainder is merged into the last section.
    """
    kept: list[list] = []
    merged = False
    for heading, text, p0, p1 in blocks:
        body = clean_text(text)
        head = clean_text(heading)[: limits.max_heading_chars] if heading else None
        if not body:
            continue
        if len(kept) >= limits.max_sections:
            last = kept[-1]
            last[1] = f"{last[1]}{SEPARATOR}{head + SEPARATOR if head else ''}{body}"
            last[3] = p1 if p1 is not None else last[3]
            merged = True
            continue
        kept.append([head, body, p0, p1])
    warnings = ("sections_merged",) if merged else ()
    sections, offset = [], 0
    for ordinal, (head, body, p0, p1) in enumerate(kept):
        sections.append(Section(ordinal, head, body, p0, p1, offset, offset + len(body)))
        offset += len(body) + len(SEPARATOR)
    if sum(len(s.text) for s in sections) > limits.max_chars:
        raise too_long(limits)
    return tuple(sections), warnings

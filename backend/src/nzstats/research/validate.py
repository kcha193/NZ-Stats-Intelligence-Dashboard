"""Deterministic checks that decide whether extracted text may be stored as a document version.

Fail closed: a login wall, paywall teaser, bot challenge, too-short page or a version much shorter
than the one already stored is rejected, and the previously stored version stays current. Error
details that are stored or shown come from `safe_detail`, which never passes on upstream text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nzstats.domain import ErrorClass, IngestError
from nzstats.research.extract import Extracted
from nzstats.research.registry import Institution

SHRINK_RATIO = 0.5  # a new version under half the previous length is treated as truncated
MARKER_WINDOW = 3000  # access walls show their message near the top of the page
_ACCESS_WALL = (
    "log in to continue", "login to continue", "sign in to continue", "please log in",
    "please sign in", "subscribe to continue", "subscribers only", "for subscribers only",
    "this content is for subscribers", "create a free account to", "to read the full report",
)  # fmt: skip
_CHALLENGE = (
    "checking your browser", "verify you are human", "are you a robot", "enable javascript and cookies",
    "request unsuccessful. incapsula", "attention required! | cloudflare", "captcha",
)  # fmt: skip
_SAFE_DETAIL = re.compile(r"^[a-z][a-z0-9_ ,.]*( \(([A-Za-z0-9_]+|[a-z ]+|> ?\d+|\d+)\))?$")


@dataclass(frozen=True)
class PreviousVersion:
    char_count: int
    text_sha256: str


def validate_document(
    inst: Institution, extracted: Extracted, *, previous: PreviousVersion | None
) -> list[str]:
    """Raises `IngestError` if the text must not be stored; otherwise returns warning codes."""
    head = f"{extracted.title or ''}\n{extracted.text[:MARKER_WINDOW]}".lower()
    if any(m in head for m in _CHALLENGE):
        raise IngestError(ErrorClass.BLOCKED, "challenge_page")
    if any(m in head for m in _ACCESS_WALL) and extracted.char_count < 10 * inst.min_text_chars:
        raise IngestError(ErrorClass.VALIDATION_FAILED, "access_wall")
    if extracted.char_count < inst.min_text_chars:
        raise IngestError(ErrorClass.VALIDATION_FAILED, "text_too_short")
    if (
        previous is not None
        and previous.text_sha256 != extracted.text_sha256
        and extracted.char_count < SHRINK_RATIO * previous.char_count
    ):
        raise IngestError(ErrorClass.VALIDATION_FAILED, "shrunk_vs_previous")
    warnings = list(extracted.warnings)
    if not extracted.title:
        warnings.append("no_title")
    return warnings


def safe_detail(exc: BaseException) -> str:
    """A short, fixed-vocabulary description safe to store and serve."""
    if isinstance(exc, IngestError):
        message = str(exc)
        if len(message) <= 80 and _SAFE_DETAIL.match(message):
            return message
        return f"{exc.error_class.value} ({type(exc).__name__})"
    return f"{ErrorClass.UNEXPECTED.value} ({type(exc).__name__})"

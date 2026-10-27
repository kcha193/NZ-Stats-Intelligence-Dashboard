"""Extraction quality of a stored document version (Phase 3D-A), for the person checking a new source.

Deterministic heuristics over the stored sections: missing or empty pages, undecodable characters (the replacement
character and private-use code points that PDF font maps produce), control characters, symbol soup, glued words (lost
spaces from column merges or OCR), spaced-out letters, running headers and footers, words split across lines, and
numeric density. Each finding has a severity: `poor` (the text is unreliable for quoting), `review` (read it before
summarising) or `info` (context only). The thresholds are judgement, not statistics, and nothing here blocks
ingestion: the grade tells a human where to look.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from nzstats.research.contract import SectionText
from nzstats.research.summarise import load_sections

EMPTY_SECTION_CHARS = 40
UNDECODABLE_POOR_RATE = 0.005  # of non-space characters
GLUED_WORD_CHARS = 25
GLUED_MIN = 3
SPACED_LETTERS_MIN = 12  # single letters inside runs of six or more
REPEAT_MIN_SECTIONS = 3
HYPHEN_BREAKS_MIN = 5
NUMERIC_HEAVY = 0.5  # digits / (letters + digits)
SYMBOL_POOR = 0.5  # letters + digits below half of non-space characters

_WORD = re.compile(r"[^\W\d_]+")
_SPACED = re.compile(r"(?:\b[^\W\d_]\b ){5,}\b[^\W\d_]\b")
_HYPHEN_BREAK = re.compile(r"[^\W\d_]-\n[^\W\d_]")
_SEVERITY = ("info", "review", "poor")


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # info, review, poor
    message: str


@dataclass(frozen=True)
class QualityReport:
    version_id: int | None
    grade: str  # ok, review, poor
    findings: tuple[Finding, ...]
    metrics: dict[str, float | int | None] = field(default_factory=dict)


def _undecodable(ch: str) -> bool:
    return ch == "�" or 0xE000 <= ord(ch) <= 0xF8FF


def _edge_lines(text: str) -> set[str]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return {lines[0], lines[-1]} if lines else set()


def assess_extraction(
    sections: Mapping[int, SectionText], *, page_count: int | None, version_id: int | None = None
) -> QualityReport:
    texts = [s.text for s in sections.values()]
    joined = "\n".join(texts)
    visible = [c for c in joined if not c.isspace()]
    n = len(visible) or 1
    letters = sum(c.isalpha() and not _undecodable(c) for c in visible)
    digits = sum(c.isdigit() for c in visible)
    undecodable = sum(_undecodable(c) for c in visible)
    control = sum(not c.isprintable() and c not in "\n\t" for c in joined)
    words = _WORD.findall(joined)
    glued = [w for w in words if len(w) >= GLUED_WORD_CHARS]
    spaced = sum(len(run.split()) for run in _SPACED.findall(joined))
    hyphen_breaks = len(_HYPHEN_BREAK.findall(joined))
    empty = [o for o, s in sections.items() if len(s.text.strip()) < EMPTY_SECTION_CHARS]
    covered = {
        p
        for s in sections.values()
        if s.page_start
        for p in range(s.page_start, (s.page_end or s.page_start) + 1)
    }
    missing = None
    if page_count and covered:
        missing = sum(p not in covered for p in range(1, page_count + 1))
    edges = Counter(line for t in texts for line in _edge_lines(t))
    repeated = [
        line for line, k in edges.items() if k >= REPEAT_MIN_SECTIONS and k * 2 >= len(texts)
    ]

    found: list[Finding] = []
    if missing:
        found.append(
            Finding(
                "missing_pages", "review", f"{missing} of {page_count} pages have no extracted text"
            )
        )
    if empty:
        found.append(Finding("empty_sections", "review",
                             f"{len(empty)} of {len(sections)} sections have under {EMPTY_SECTION_CHARS} characters"
                             " (scanned images, charts or blank pages)"))  # fmt: skip
    if undecodable:
        severity = "poor" if undecodable / n > UNDECODABLE_POOR_RATE else "review"
        found.append(Finding("undecodable_characters", severity,
                             f"{undecodable} replacement or private-use characters: the PDF's font map is incomplete,"
                             " so numbers and quotes may be wrong"))  # fmt: skip
    if control:
        found.append(
            Finding("control_characters", "review", f"{control} control characters in the text")
        )
    if visible and (letters + digits) / n < SYMBOL_POOR:
        found.append(
            Finding("symbol_soup", "poor", "under half of the characters are letters or digits")
        )
    if len(glued) >= GLUED_MIN:
        found.append(Finding("glued_words", "review",
                             f"{len(glued)} words of {GLUED_WORD_CHARS}+ letters: spaces were probably lost"
                             " (column merge or OCR)"))  # fmt: skip
    if spaced >= SPACED_LETTERS_MIN:
        found.append(Finding("spaced_letters", "review",
                             f"{spaced} letters stand alone in runs separated by spaces: words were split apart"))  # fmt: skip
    if repeated:
        found.append(Finding("repeated_lines", "info",
                             f"{len(repeated)} running header or footer lines, the most frequent on"
                             f" {max(edges[line] for line in repeated)} of {len(texts)} sections"))  # fmt: skip
    if hyphen_breaks >= HYPHEN_BREAKS_MIN:
        found.append(Finding("hyphen_breaks", "info",
                             f"{hyphen_breaks} words hyphenated across lines; a quote spanning one will not match"))  # fmt: skip
    if letters + digits and digits / (letters + digits) > NUMERIC_HEAVY:
        found.append(Finding("numeric_heavy", "info",
                             "mostly numbers (tables): check that rows and columns kept their order"))  # fmt: skip

    worst = max((_SEVERITY.index(f.severity) for f in found), default=-1)
    grade = {-1: "ok", 0: "ok", 1: "review", 2: "poor"}[worst]
    metrics: dict[str, float | int | None] = {
        "sections": len(sections), "characters": len(visible), "page_count": page_count,
        "missing_pages": missing, "empty_sections": len(empty), "undecodable": undecodable,
        "letter_ratio": round(letters / n, 3), "digit_ratio": round(digits / n, 3), "glued_words": len(glued),
        "spaced_letters": spaced, "repeated_lines": len(repeated), "hyphen_breaks": hyphen_breaks,
    }  # fmt: skip
    return QualityReport(version_id, grade, tuple(found), metrics)


def version_quality(conn: sqlite3.Connection, version_id: int) -> QualityReport | None:
    row = conn.execute(
        "SELECT page_count FROM research_document_version WHERE id = ?", (version_id,)
    ).fetchone()
    if row is None:
        return None
    return assess_extraction(
        load_sections(conn, version_id), page_count=row["page_count"], version_id=version_id
    )

"""Scan text bound for a public site for things that must never be published."""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("e-mail address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    (
        "filesystem path",
        re.compile(r"(?<![\w.:/-])(?:/Users/|/home/|/var/|/tmp/|/data/|/app/|[A-Za-z]:\\\\)\S+"),
    ),
    ("database file", re.compile(r"\.(?:db|sqlite3?)(?:-wal|-shm)?\b|\bsqlite\b", re.IGNORECASE)),
    (
        "credential word",
        re.compile(r"\b(?:api[_-]?key|secret|passw(?:or)?d|bearer|authorization)\b", re.IGNORECASE),
    ),
    ("stack trace", re.compile(r"Traceback \(most recent call last\)|\bFile \"[^\"]+\", line \d+")),
    ("environment variable", re.compile(r"\bNZSTATS_[A-Z_]+|\bNETLIFY_[A-Z_]+")),
)


def scan_for_leaks(text: str, *, extra: tuple[str, ...] = ()) -> list[str]:
    """Human-readable findings; empty means clean. `extra` are literal strings that must not appear."""
    findings = [
        f"{label}: {m.group(0)[:60]!r}"
        for label, pattern in _PATTERNS
        for m in [pattern.search(text)]
        if m
    ]
    findings += [f"forbidden text: {needle!r}" for needle in extra if needle and needle in text]
    return findings

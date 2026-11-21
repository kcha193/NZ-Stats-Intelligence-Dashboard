"""The owner's canonical series mapping for ANZ's forecasts workbook (Phase 4AR; design in Phase 4AQ §3).

A mapping is a small JSON file the owner writes with `tables map` (positions in, exact workbook text filled in locally).
It holds ANZ titles, so it lives under the Git-ignored `data/` directory and never enters a hosted model's context.

This module only parses and checks the file itself: an exact schema, exact key sets, strict types, and no duplicate
series. The checks against a workbook (hash, structure, unit evidence, sheet context) are in `xlsx_anz`. Any failure
refuses the whole file with one fixed code, so a partly valid mapping is never applied. Its identity is the SHA-256 of
the exact file bytes, which the evidence and the owner's confirmation code both carry.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

SCHEMA = "anz-workbook-mapping-1"
MAX_BYTES = 256 * 1024
INDICATORS = ("gdp", "cpi_inflation", "unemployment")  # OCR is never mapped: its unit is unverified
BASES = ("quarterly", "annual", "annual_average")
CLASSIFICATIONS = ("editorial", "substantive")

_TOP_KEYS = frozenset(
    {
        "schema",
        "workbook_sha256",
        "reviewer",
        "decided_on",
        "published_on",
        "series",
        "sheet_context",
    }
)
_ENTRY_KEYS = frozenset(
    {
        "indicator",
        "basis",
        "sheet",
        "sheet_name",
        "block",
        "block_title",
        "column",
        "unit_header",
        "unit_evidence",
    }
)
_EVIDENCE_KEYS = frozenset({"sheet", "cell", "text"})
_PUBLISHED_KEYS = frozenset({"date", "sheet", "cell", "text"})
_CONTEXT_KEYS = frozenset({"sheet", "sheet_name", "classification"})
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COLUMN = re.compile(r"[A-Z]{1,3}")
_CELL = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class MappingRefused(Exception):
    """The whole mapping is refused; `code` is a fixed word, never file text."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def column_number(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def cell_position(a1: str) -> tuple[int, int] | None:
    """(row, column) of an A1 address, or None when it is not one."""
    match = _CELL.fullmatch(a1)
    return None if match is None else (int(match[2]), column_number(match[1]))


@dataclass(frozen=True)
class UnitEvidence:
    sheet: int
    cell: str
    text: str


@dataclass(frozen=True)
class MappingEntry:
    indicator: str
    basis: str
    sheet: int
    sheet_name: str
    block: int
    block_title: str
    column: str
    unit_header: str
    unit_evidence: UnitEvidence | None
    raw: dict[str, Any]

    @property
    def col(self) -> int:
        return column_number(self.column)


@dataclass(frozen=True)
class AnzMapping:
    sha256: str
    workbook_sha256: str
    reviewer: str
    decided_on: str
    published_on: dict[str, Any] | None
    series: tuple[MappingEntry, ...]
    sheet_context: dict[
        tuple[int, str], str
    ]  # (sheet position, exact sheet name) -> classification


def _invalid() -> MappingRefused:
    return MappingRefused("mapping_invalid")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _invalid()
        out[key] = value
    return out


def _obj(value: Any, keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise _invalid()
    return value


def _int(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= 10_000:  # bool is not a position
        raise _invalid()
    return value


def _text(value: Any, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > 2_000:
        raise _invalid()
    return value


def _iso_date(value: Any) -> str:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise _invalid()
    try:
        date.fromisoformat(value)
    except ValueError:
        raise _invalid() from None
    return value


def _choice(value: Any, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise _invalid()
    return value


def _cell(value: Any) -> str:
    if not isinstance(value, str) or cell_position(value) is None:
        raise _invalid()
    return value


def _entry(raw: Any) -> MappingEntry:
    raw = _obj(raw, _ENTRY_KEYS)
    indicator = _choice(raw["indicator"], INDICATORS)
    column = raw["column"]
    if not isinstance(column, str) or not _COLUMN.fullmatch(column):
        raise _invalid()
    sheet = _int(raw["sheet"])
    evidence = None
    if raw["unit_evidence"] is not None:
        ev = _obj(raw["unit_evidence"], _EVIDENCE_KEYS)
        # Only unemployment may take its unit from a note, and only from its own sheet.
        if indicator != "unemployment" or _int(ev["sheet"]) != sheet:
            raise _invalid()
        evidence = UnitEvidence(ev["sheet"], _cell(ev["cell"]), _text(ev["text"]))
    return MappingEntry(
        indicator=indicator,
        basis=_choice(raw["basis"], BASES),
        sheet=sheet,
        sheet_name=_text(raw["sheet_name"]),
        block=_int(raw["block"]),
        block_title=_text(raw["block_title"]),
        column=column,
        unit_header=_text(raw["unit_header"], empty=True),
        unit_evidence=evidence,
        raw=raw,
    )


def parse_mapping(body: bytes) -> AnzMapping:
    """The checked mapping, or MappingRefused with `mapping_invalid` or `mapping_duplicate`."""
    if not body or len(body) > MAX_BYTES:
        raise _invalid()
    try:
        doc = json.loads(body.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise _invalid() from None
    doc = _obj(doc, _TOP_KEYS)
    if doc["schema"] != SCHEMA or doc["reviewer"] != "owner":
        raise _invalid()
    workbook_sha256 = doc["workbook_sha256"]
    if not isinstance(workbook_sha256, str) or not _SHA256.fullmatch(workbook_sha256):
        raise _invalid()
    published = doc["published_on"]
    if published != "not_stated":
        published = _obj(published, _PUBLISHED_KEYS)
        (
            _iso_date(published["date"]),
            _int(published["sheet"]),
            _cell(published["cell"]),
            _text(published["text"]),
        )
    if (
        not isinstance(doc["series"], list)
        or not doc["series"]
        or not isinstance(doc["sheet_context"], list)
    ):
        raise _invalid()
    series = tuple(_entry(e) for e in doc["series"])
    context: dict[tuple[int, str], str] = {}
    seen_sheets: set[int] = set()
    for raw in doc["sheet_context"]:
        raw = _obj(raw, _CONTEXT_KEYS)
        sheet = _int(raw["sheet"])
        key = (sheet, _text(raw["sheet_name"]))
        classification = _choice(raw["classification"], CLASSIFICATIONS)
        if sheet in seen_sheets:
            raise MappingRefused("mapping_duplicate")
        seen_sheets.add(sheet)
        context[key] = classification
    _check_duplicates(series)
    return AnzMapping(
        sha256=hashlib.sha256(body).hexdigest(),
        workbook_sha256=workbook_sha256,
        reviewer=doc["reviewer"],
        decided_on=_iso_date(doc["decided_on"]),
        published_on=None if published == "not_stated" else published,
        series=series,
        sheet_context=context,
    )


def _check_duplicates(series: tuple[MappingEntry, ...]) -> None:
    """One column per (indicator, basis), one entry per column, and one headline block per indicator."""
    pairs = [(e.indicator, e.basis) for e in series]
    columns = [(e.sheet, e.col) for e in series]
    blocks: dict[str, set[tuple[int, int]]] = {}
    for e in series:
        blocks.setdefault(e.indicator, set()).add((e.sheet, e.block))
    if (
        len(set(pairs)) != len(pairs)
        or len(set(columns)) != len(columns)
        or any(len(b) > 1 for b in blocks.values())
    ):
        raise MappingRefused("mapping_duplicate")

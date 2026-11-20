"""Neutral table model every parser is adapted to, and the ground truth the synthetic cases carry."""

from __future__ import annotations

from dataclasses import dataclass, field

BBox = tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF points, origin bottom-left


@dataclass(frozen=True)
class BenchTable:
    page: int  # 1-based
    bbox: BBox
    grid: list[list[str]]  # rows top to bottom, cells left to right
    header_rows: int | None = None  # None when the parser has no header concept
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TruthTable:
    page: int
    bbox: BBox
    row_labels: list[str]
    col_headers: list[list[str]]  # per value column: its header fragments, top to bottom
    values: dict[tuple[int, int], str]  # (row, col) -> printed text
    stacked: list[int] = field(default_factory=list)  # columns whose header is stacked across the period line
    markers: list[tuple[int, str]] = field(default_factory=list)  # (row, marker digit) on a row label
    value_markers: dict[tuple[int, int], str] = field(default_factory=dict)  # (row, col) -> marker printed on a value
    notes: list[str] = field(default_factory=list)


Item = tuple[float, float, float, str]  # x_left, baseline y, font size, text
Line = tuple[float, float, float, float]


@dataclass(frozen=True)
class Case:
    name: str
    pdf: bytes
    truth: list[TruthTable]
    items: list[Item]
    lines: list[Line]

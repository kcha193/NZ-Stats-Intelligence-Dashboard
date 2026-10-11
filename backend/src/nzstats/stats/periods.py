from __future__ import annotations

import calendar


def parse_month(period: str) -> tuple[int, int]:
    try:
        year_s, month_s = period.split("-")
        year, month = int(year_s), int(month_s)
    except ValueError as exc:
        raise ValueError(f"invalid month period: {period!r}") from exc
    if not 1 <= month <= 12 or len(year_s) != 4:
        raise ValueError(f"invalid month period: {period!r}")
    return year, month


def add_months(period: str, n: int) -> str:
    year, month = parse_month(period)
    idx = year * 12 + (month - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def months_between(a: str, b: str) -> int:
    ya, ma = parse_month(a)
    yb, mb = parse_month(b)
    return (yb - ya) * 12 + (mb - ma)


def month_range(start: str, end: str) -> list[str]:
    return [add_months(start, i) for i in range(months_between(start, end) + 1)]


def month_label(period: str) -> str:
    year, month = parse_month(period)
    return f"{calendar.month_name[month]} {year}"

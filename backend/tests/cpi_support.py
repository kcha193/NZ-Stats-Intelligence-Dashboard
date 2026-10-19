"""Captured official CPI releases (Dec 2025, Mar 2026, Jun 2026) for offline tests."""

from __future__ import annotations

from nzstats.sources.release_page import ReleasePage, parse_release_page
from tests.conftest import fixture_bytes, fixture_text
from tests.support import BASE

KINDS = ("index_numbers", "seasonally_adjusted", "tradables")


def page(month: str = "2026-06") -> ReleasePage:
    return parse_release_page(fixture_text(f"cpi_{month}_page.html"), BASE)


def files(month: str = "2026-06") -> dict[str, bytes]:
    names = {"index_numbers": "cpi_index_numbers", "seasonally_adjusted": "cpi_seasonally_adjusted"}
    return {names.get(k, "cpi_tradables"): fixture_bytes(f"cpi_{month}_{k}.csv") for k in KINDS}


def edited(source: dict[str, bytes], kind: str, old: str, new: str) -> dict[str, bytes]:
    """A copy of `source` with `old` replaced by `new` in one file; fails if `old` is absent."""
    text = source[kind].decode("utf-8")
    assert old in text, f"{old!r} not found in {kind}"
    return {**source, kind: text.replace(old, new, 1).encode("utf-8")}

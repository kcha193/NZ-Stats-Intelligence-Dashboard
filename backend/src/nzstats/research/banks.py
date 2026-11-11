"""Bank series adapters (Phase 4AE): which report series a document belongs to, its kind and expected cadence.

An adapter identifies and classifies; it never decides whether anything may be fetched, stored, processed or shown.
Those are the registry's separate permission decisions (`registry.Institution`), and no permission data lives here.
A bank without an adapter is simply unsupported for series-aware features, and its documents have kind `other`.

Dates and listing parsing stay with the registry (`url_date_regex`, `dates.py`, `discover.parse_html_links`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

ReportKind = Literal["outlook", "weekly", "commentary", "other"]


@dataclass(frozen=True)
class Series:
    key: str
    name: str
    report_kind: ReportKind
    cadence_days: int  # a new publication of this series is due at least this often
    url_pattern: str | None = None
    title_pattern: str | None = None

    def matches(self, url: str, title: str) -> bool:
        if self.url_pattern and re.search(self.url_pattern, url):
            return True
        return bool(self.title_pattern and re.search(self.title_pattern, title, re.IGNORECASE))


@dataclass(frozen=True)
class BankAdapter:
    key: str
    series: tuple[Series, ...]

    def series_of(self, url: str, title: str) -> Series | None:
        return next((s for s in self.series if s.matches(url, title)), None)

    def canonical_url(self, url: str) -> str:
        return canonical_url(url)


def canonical_url(url: str) -> str:
    """Lowercase scheme and host, no query, fragment or trailing slash on the path."""
    parts = urlsplit(url)
    path = parts.path.rstrip("/") if len(parts.path) > 1 else parts.path
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


ADAPTERS: Mapping[str, BankAdapter] = {
    "anz": BankAdapter("anz", (
        Series("economic_outlook", "Quarterly Economic Outlook", "outlook", 100,
               url_pattern=r"/economics-and-market-research/\d{4}/ANZ-QEO-\d{8}\.pdf$"),
    )),
    "asb": BankAdapter("asb", (
        Series("quarterly_economic_forecasts", "Quarterly Economic Forecasts", "outlook", 100,
               url_pattern=r"/documents/economic-research/quarterly-economic-forecasts/"),
        Series("economic_weekly", "Economic Weekly", "weekly", 10,
               url_pattern=r"/documents/economic-research/economic-weekly/"),
    )),
    "westpac": BankAdapter("westpac", (
        Series("weekly_commentary", "Weekly Commentary", "weekly", 10,
               url_pattern=r"/economic-reports/weekly-commentary/Weekly-Commentary_"),
    )),
}  # fmt: skip


def adapter_for(key: str, adapters: Mapping[str, BankAdapter] = ADAPTERS) -> BankAdapter | None:
    return adapters.get(key)


def report_kind_of(
    key: str, url: str, title: str, adapters: Mapping[str, BankAdapter] = ADAPTERS
) -> ReportKind:
    adapter = adapter_for(key, adapters)
    series = adapter.series_of(url, title) if adapter else None
    return series.report_kind if series else "other"

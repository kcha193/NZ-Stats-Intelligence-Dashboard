"""Derived country ranking: sum of the last N monthly arrivals by country of last residence."""

from __future__ import annotations

import sqlite3

from nzstats.domain import ObsStatus
from nzstats.models import CountriesOut, CountryRank
from nzstats.stats.periods import add_months, month_range
from nzstats.store import repo

NOTE = (
    "Derived: Stats NZ's published monthly estimates summed over the window. Months absent "
    "from the source are treated as zero. Regions and 'Not Stated' are not ranked as "
    "countries."
)
CATEGORIES = ("migration:country", "migration:region", "migration:unallocated")


def _first_country_period(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT MIN(o.period) FROM observation o JOIN vintage v ON v.id = o.vintage_id"
        " JOIN series s ON s.id = v.series_id WHERE s.category = 'migration:country'"
    ).fetchone()
    return row[0]


def rank_countries(conn: sqlite3.Connection, *, months: int = 12, top: int = 15) -> CountriesOut:
    totals = {p: pt.value for p, pt in repo.latest_points(conn, "mig.m.arrivals").items()}
    first_stored = _first_country_period(conn)
    if not totals or first_stored is None:
        return CountriesOut(
            available=False,
            months=months,
            period_start=None,
            period_end=None,
            total=None,
            countries=[],
            regions=[],
            unallocated=None,
            derived=True,
            note="No country data has been ingested yet.",
        )
    end = max(totals)
    start = add_months(end, -(months - 1))
    window = month_range(start, end)
    prior_window = month_range(add_months(start, -months), add_months(start, -1))
    prior_stored = prior_window[0] >= first_stored  # prior window fully inside stored history
    total = sum(totals.get(p, 0.0) for p in window)

    groups: dict[str, list[CountryRank]] = {c: [] for c in CATEGORIES}
    for row in repo.series_overview(conn, "migration:"):
        if row["category"] not in groups:
            continue
        points = repo.latest_points(conn, row["key"])
        if not points:
            continue
        value = sum(points[p].value for p in window if p in points)
        provisional = any(points[p].status is ObsStatus.PROVISIONAL for p in window if p in points)
        prior = sum(points[p].value for p in prior_window if p in points) if prior_stored else None
        name = (
            row["name"].removeprefix("Migrant arrivals from ").removesuffix(" (monthly estimate)")
        )
        groups[row["category"]].append(
            CountryRank(
                name=name,
                series_key=row["key"],
                value=value,
                prior_value=prior,
                change=None if prior is None else value - prior,
                change_percent=(
                    None if prior is None or prior <= 0 else (value - prior) / prior * 100
                ),
                share_percent=(value / total * 100) if total > 0 else None,
                provisional=provisional,
            )
        )

    def ordered(items: list[CountryRank]) -> list[CountryRank]:
        return sorted(items, key=lambda c: (-c.value, c.name))

    unallocated = ordered(groups["migration:unallocated"])
    return CountriesOut(
        available=bool(groups["migration:country"]),
        months=months,
        period_start=start,
        period_end=end,
        total=total,
        countries=ordered(groups["migration:country"])[:top],
        regions=ordered(groups["migration:region"]),
        unallocated=unallocated[0] if unallocated else None,
        derived=True,
        note=NOTE,
    )

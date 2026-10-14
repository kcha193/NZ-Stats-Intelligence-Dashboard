"""Derived country ranking: sum of the last N monthly arrivals by country of last residence."""

from __future__ import annotations

import sqlite3

from nzstats.clock import to_akl_iso
from nzstats.domain import ObsStatus
from nzstats.models import CountriesOut, CountryProvenance, CountryRank
from nzstats.stats.periods import add_months, month_range
from nzstats.store import repo

NOTE = (
    "Derived: Stats NZ's published monthly estimates summed over the window. Months absent "
    "from the source are treated as zero. Regions and 'Not Stated' are not ranked as "
    "countries."
)
CATEGORIES = ("migration:country", "migration:region", "migration:unallocated")


def rank_countries(conn: sqlite3.Connection, *, months: int = 12, top: int = 15) -> CountriesOut:
    # Every place is read from the same ingested bundle as the total. Stats NZ's country file is
    # sparse, so a place missing from the latest bundle has nothing in that release (zero), and an
    # older vintage of it must not leak into a window ranked from the newest release.
    bundle = repo.latest_bundle(conn, "mig.m.arrivals")
    totals = {
        p: pt.value
        for p, pt in (repo.bundle_points(conn, "mig.m.arrivals", bundle) if bundle else {}).items()
    }
    provenance = None
    if bundle:
        # Match the already selected bundle, including its total's capture timestamp. A second
        # latest-release query could drift to a correction or another release during this request.
        metadata = repo.bundle_vintage(conn, "mig.m.arrivals", *bundle)
        release = repo.get_release_by_id(conn, bundle[0])
        if metadata:
            provenance = CountryProvenance(
                release_key=metadata.release_key,
                title=metadata.title,
                published_at=to_akl_iso(metadata.published_at) if metadata.published_at else None,
                source_url=release["page_url"] if release else None,
                captured_at=to_akl_iso(metadata.captured_at) if metadata.captured_at else None,
                bundle_sha256=bundle[1],
            )
    rows = [r for r in repo.series_overview(conn, "migration:") if r["category"] in CATEGORIES]
    points_by_key = {
        r["key"]: repo.bundle_points(conn, r["key"], bundle) if bundle else {} for r in rows
    }
    country_firsts = [
        min(points_by_key[r["key"]])
        for r in rows
        if r["category"] == "migration:country" and points_by_key[r["key"]]
    ]
    first_stored = min(country_firsts) if country_firsts else None
    if not totals or first_stored is None:
        return CountriesOut(
            provenance=provenance,
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
    prior_stored = prior_window[0] >= first_stored  # prior window fully inside the latest vintage
    total = sum(totals.get(p, 0.0) for p in window)

    groups: dict[str, list[CountryRank]] = {c: [] for c in CATEGORIES}
    for row in rows:
        points = points_by_key[row["key"]]
        value = sum(points[p].value for p in window if p in points)
        provisional = any(points[p].status is ObsStatus.PROVISIONAL for p in window if p in points)
        prior = sum(points[p].value for p in prior_window if p in points) if prior_stored else None
        prior_provisional = (
            any(points[p].status is ObsStatus.PROVISIONAL for p in prior_window if p in points)
            if prior_stored
            else None
        )
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
                prior_provisional=prior_provisional,
            )
        )

    def ordered(items: list[CountryRank]) -> list[CountryRank]:
        return sorted(items, key=lambda c: (-c.value, c.name))

    unallocated = ordered(groups["migration:unallocated"])
    return CountriesOut(
        provenance=provenance,
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

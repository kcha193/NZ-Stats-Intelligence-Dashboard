"""First-published against latest figures of a quarterly series, from the stored release vintages.

The baseline is each release's earliest inserted vintage. Original-publication labels additionally require its
own quarter, a release-day original-source capture and no earlier bundle. Other captures remain earliest stored;
no later vintage silently becomes an original publication.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass

from nzstats.models import FirstLatestRow, FirstLatestTable
from nzstats.stats.gdp import round_1dp
from nzstats.stats.periods import add_months
from nzstats.store import repo
from nzstats.store.repo import supports_first_publication


@dataclass(frozen=True)
class ReleaseValues:
    title: str
    reference_period: str | None
    values: dict[str, float]
    is_publication: bool


def first_stored(
    conn: sqlite3.Connection, slug: str, key: str, published_at: str
) -> list[ReleaseValues]:
    """Each release of `slug` published up to `published_at`, oldest first, with `key` as first stored."""
    references = dict(
        conn.execute(
            "SELECT release_key, reference_period FROM release WHERE series_slug = ?", (slug,)
        ).fetchall()
    )
    earliest: dict[str, repo.VintageInfo] = {}
    for v in repo.list_vintages(conn, key):
        if v.published_at > published_at:
            continue  # a later release is not "first published" for this view
        if v.release_key not in earliest or v.vintage_id < earliest[v.release_key].vintage_id:
            earliest[v.release_key] = v
    ordered = sorted(earliest.values(), key=lambda v: (v.published_at, v.vintage_id))
    return [
        ReleaseValues(
            v.title,
            references.get(v.release_key),
            {p: pt.value for p, pt in repo.vintage_points(conn, v.vintage_id).items()},
            supports_first_publication(conn, v),
        )
        for v in ordered
    ]


def first_latest_table(
    conn: sqlite3.Connection,
    slug: str,
    row: sqlite3.Row,
    key: str,
    label: str,
    latest: Mapping[str, float],
    *,
    quarters: int = 8,
) -> FirstLatestTable:
    """The last `quarters` quarters of `key`: first published (or earliest stored) against `latest`."""
    releases = first_stored(conn, slug, key, row["published_at"])
    if len(releases) < 2:
        return FirstLatestTable(
            series_key=key,
            label=label,
            available=False,
            note="Only one release is stored, so first-published and latest figures cannot be compared.",
            rows=[],
        )
    ref = max(latest)
    rows = []
    for period in (add_months(ref, -3 * k) for k in range(quarters)):
        if period not in latest:
            continue
        own = next(
            (r for r in releases if r.reference_period == period and period in r.values), None
        )
        first = own or next((r for r in releases if period in r.values), None)
        if first is None:
            continue
        rows.append(
            FirstLatestRow(
                period=period,
                first_value=first.values[period],
                first_release=first.title,
                first_is_publication=own is not None and own.is_publication,
                latest_value=latest[period],
                latest_release=row["title"],
                revision=round_1dp(latest[period] - first.values[period]),
            )
        )
    return FirstLatestTable(
        series_key=key,
        label=label,
        available=True,
        note="First published requires an uncorrected source captured on the quarter's release day. "
        "Late captures, corrected files and missing original releases are marked as earliest stored; "
        f"their differences are stored-vintage changes, not verified revisions since first publication. Latest: {row['title']}.",
        rows=rows,
    )

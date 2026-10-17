from __future__ import annotations

import sqlite3

from nzstats.clock import to_akl_iso
from nzstats.domain import Point
from nzstats.models import (
    Coverage,
    RevisionHistoryRow,
    RevisionRowOut,
    RevisionsOut,
    SeriesOut,
    VintageOut,
)
from nzstats.stats.revision import revisions, summarise
from nzstats.store import repo


def series_out(row: sqlite3.Row, n_vintages: int, latest_period: str | None) -> SeriesOut:
    return SeriesOut(
        key=row["key"],
        name=row["name"],
        unit=row["unit"],
        frequency=row["frequency"],
        adjustment=row["seasonal_adjustment"],
        category=row["category"],
        definition=row["definition"],
        definition_id=row["definition_id"],
        latest_period=latest_period,
        n_vintages=n_vintages,
    )


def vintage_out(conn: sqlite3.Connection, v: repo.VintageInfo) -> VintageOut:
    return VintageOut(
        superseded=repo.vintage_superseded(conn, v.vintage_id),
        release_key=v.release_key,
        title=v.title,
        published_at=to_akl_iso(v.published_at),
        captured_at=to_akl_iso(v.captured_at),
        source_kind=v.source_kind,
        layout_version=v.layout_version,
    )


def _points(conn: sqlite3.Connection, v: repo.VintageInfo) -> dict[str, Point]:
    return repo.vintage_points(conn, v.vintage_id)


def _coverage(vintages: list[repo.VintageInfo]) -> Coverage:
    if not vintages:
        return Coverage(
            kind="none",
            n_vintages=0,
            earliest_release=None,
            note="No data has been ingested for this series yet.",
        )
    kinds = {v.source_kind for v in vintages}
    earliest = vintages[0]
    if kinds == {"release_files"}:
        note = (
            f"Vintages are the official data files published with each Stats NZ release: "
            f"{len(vintages)} stored, earliest {earliest.title}. Revisions before that "
            f"release cannot be observed."
        )
        kind = "release_files"
    else:
        note = (
            f"Revision history only covers snapshots captured since this monitor began "
            f"operating (earliest {earliest.title})."
        )
        kind = "snapshot"
    if len(vintages) < 2:
        note += " At least two vintages are needed to show revisions."
    return Coverage(kind=kind, n_vintages=len(vintages), earliest_release=earliest.title, note=note)


def revision_view(
    conn: sqlite3.Connection,
    series_key: str,
    *,
    base_release_key: str | None = None,
    compare_release_key: str | None = None,
) -> RevisionsOut | None:
    row = repo.get_series_row(conn, series_key)
    if row is None:
        return None
    vintages = repo.list_vintages(conn, series_key)
    latest = max(repo.vintage_points(conn, vintages[-1].vintage_id)) if vintages else None
    series = series_out(row, len(vintages), latest)
    coverage = _coverage(vintages)
    if len(vintages) < 2:
        return RevisionsOut(
            series=series,
            coverage=coverage,
            base=None,
            compare=None,
            source_url=None,
            n_common=0,
            n_revised=0,
            rows=[],
            history=[],
        )

    by_key = {v.release_key: v for v in vintages}  # later vintages of a release win
    compare = by_key.get(compare_release_key) if compare_release_key else vintages[-1]
    if compare is None:
        return None
    if base_release_key:
        base = by_key.get(base_release_key)
    else:
        # `vintages` is in publication order (insertion order is not: a backfill can ingest an older
        # release after a newer one), so the default base is the vintage just before `compare`.
        position = vintages.index(compare)
        base = vintages[position - 1] if position else None
    if base is None:
        return None

    def compatible_pair(a, b):
        left = repo.get_series_row(conn, series_key, a.vintage_id)
        right = repo.get_series_row(conn, series_key, b.vintage_id)
        return all(
            left[k] == right[k]
            for k in ("unit", "frequency", "seasonal_adjustment", "definition_id", "definition")
        )

    series = series_out(
        repo.get_series_row(conn, series_key, compare.vintage_id), len(vintages), latest
    )
    if not compatible_pair(base, compare):
        coverage = coverage.model_copy(
            update={
                "note": coverage.note
                + " Comparison withheld: vintage measurement definitions are incompatible."
            }
        )
        return RevisionsOut(
            series=series,
            coverage=coverage,
            base=None,
            compare=None,
            source_url=None,
            n_common=0,
            n_revised=0,
            rows=[],
            history=[],
        )

    revs = revisions(_points(conn, base), _points(conn, compare))
    summary = summarise(revs)
    rows = [
        RevisionRowOut(
            period=r.period,
            original=r.original,
            revised=r.revised,
            absolute=r.absolute,
            percent=r.percent,
            original_status=r.original_status.value,
            revised_status=r.revised_status.value,
        )
        for r in revs
        if r.absolute != 0
    ]

    history = []
    for older, newer in zip(vintages, vintages[1:], strict=False):
        if not compatible_pair(older, newer):
            continue
        s = summarise(revisions(_points(conn, older), _points(conn, newer)))
        history.append(
            RevisionHistoryRow(
                release_key=newer.release_key,
                title=newer.title,
                published_at=to_akl_iso(newer.published_at),
                n_common=s.n_common,
                n_revised=s.n_revised,
                mean_abs=s.mean_abs,
                max_abs_period=s.max_abs.period if s.max_abs else None,
                max_abs=s.max_abs.absolute if s.max_abs else None,
            )
        )
    release = repo.get_release(conn, compare.release_key)
    return RevisionsOut(
        series=series,
        coverage=coverage,
        base=vintage_out(conn, base),
        compare=vintage_out(conn, compare),
        source_url=release["page_url"] if release else None,
        n_common=summary.n_common,
        n_revised=summary.n_revised,
        rows=rows,
        history=history,
    )

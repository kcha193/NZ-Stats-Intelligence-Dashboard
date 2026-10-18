"""Evidence-grounded ECT release analysis and a single-bundle dashboard projection."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from nzstats.adapters.ect.series import INDUSTRIES, REQUIRED, SLUG
from nzstats.clock import to_akl_iso
from nzstats.domain import Adjustment, Frequency, Observation, SeriesDef
from nzstats.insights.migration import _corrections
from nzstats.insights.revisions import revision_view, series_out, vintage_out
from nzstats.insights.summary import release_summary
from nzstats.models import (
    ChangeOut,
    Decomposition,
    EctDashboardOut,
    Evidence,
    Insight,
    Kpi,
    Methodology,
    Metric,
    PointOut,
    PreviousComparison,
    ReleaseAnalysis,
    RevisionBlock,
    SeriesDataOut,
)
from nzstats.stats.changes import lagged_change
from nzstats.stats.periods import month_label
from nzstats.store import repo

CAVEATS = [
    "ECT covers New Zealand-based electronic card transactions supplied by participating providers; "
    "it is not all retail sales or all household consumption. Unclassified transactions are excluded "
    "and provider coverage and merchant classifications can change.",
    "Spending is nominal NZD, not adjusted for inflation. Values are expressed in NZD millions; "
    "counts are transactions and mean transaction values are NZD.",
    "Actual means unadjusted. Seasonally adjusted series remove seasonal/calendar effects; trend "
    "series smooth short-term movements. Seasonal and trend estimates can be revised.",
    "Retail includes consumables, durables, hospitality, apparel, motor vehicles excluding fuel, "
    "and fuel. Core retail excludes motor vehicles and fuel. Total ECT also includes services "
    "and non-retail excluding services.",
    "Seasonally adjusted components are independently adjusted and may not sum to aggregates. "
    "Composition charts use actual industry levels without stacking overlapping aggregates.",
    "Quarterly observations are the official ECTQ source series, never sums of adjusted months. "
    "Quarterly changes compare the previous quarter, not the previous month.",
    "Historical observations in one download are one publication vintage. Revision history covers "
    "only distinct publications or corrections actually captured by this monitor.",
    "Official CSV levels are rounded to 0.1 million; movements can differ from published headlines "
    "by source rounding. R (revised) statuses are shown as unknown, not final; all estimates may change.",
]


def metric(
    definition: SeriesDef, observations: Sequence[Observation | repo.ObservationRow]
) -> Metric:
    values = {o.period: o.value for o in observations}
    latest = max(values)
    last = next(o for o in observations if o.period == latest)
    quarterly = definition.frequency.value == "quarterly"

    def change(lag):
        c = lagged_change(values, latest, lag)
        return (
            ChangeOut(
                label=f"vs {month_label(c.comparison_period)}" + (" quarter" if quarterly else ""),
                comparison_period=c.comparison_period,
                previous=c.previous,
                absolute=c.absolute,
                percent=c.percent,
            )
            if c
            else None
        )

    return Metric(
        series_key=definition.key,
        label=definition.name,
        value=last.value,
        unit=definition.unit,
        frequency=definition.frequency.value,
        period=latest,
        period_label=("Quarter ended " if quarterly else "") + month_label(latest),
        status=last.status.value,
        std_error=None,
        change_prior=change(3 if quarterly else 1),
        change_year_ago=change(12),
    )


def build_ect_overview_kpi(conn: sqlite3.Connection) -> tuple[Kpi, str] | None:
    """Project the latest ECT retail KPI without materialising the full dashboard payload."""
    row = conn.execute(
        "SELECT r.* FROM release r WHERE r.series_slug=? AND EXISTS "
        "(SELECT 1 FROM vintage v WHERE v.release_id=r.id) ORDER BY r.published_at DESC LIMIT 1",
        (SLUG,),
    ).fetchone()
    if row is None:
        return None
    bundle = repo.release_bundle(conn, row["id"])
    if bundle is None:
        return None
    vintage = repo.bundle_vintage(conn, "ect.m.sa.retail.value", row["id"], bundle)
    if vintage is None:
        return None
    stored = repo.get_series_row(conn, "ect.m.sa.retail.value", vintage.vintage_id)
    observations = list(repo.vintage_observations(conn, vintage.vintage_id).values())
    if stored is None or not observations:
        return None
    definition = SeriesDef(
        key=stored["key"],
        name=stored["name"],
        unit=stored["unit"],
        frequency=Frequency(stored["frequency"]),
        adjustment=Adjustment(stored["seasonal_adjustment"]),
        definition=stored["definition"],
        definition_id=stored["definition_id"],
        category=stored["category"],
        source_url=stored["source_url"],
    )
    return (
        Kpi(
            metric=metric(definition, observations),
            release_id=row["id"],
            published_at=to_akl_iso(row["published_at"]),
            source_url=row["page_url"],
        ),
        to_akl_iso(vintage.captured_at),
    )


def build_ect_dashboard(
    conn: sqlite3.Connection, release_id: int | None = None
) -> EctDashboardOut | None:
    if release_id is None:
        row = conn.execute(
            "SELECT r.* FROM release r WHERE r.series_slug=? AND EXISTS "
            "(SELECT 1 FROM vintage v WHERE v.release_id=r.id) ORDER BY r.published_at DESC LIMIT 1",
            (SLUG,),
        ).fetchone()
    else:
        row = repo.get_release_by_id(conn, release_id)
    if row is None or row["series_slug"] != SLUG:
        return None
    bundle = repo.release_bundle(conn, row["id"])
    if bundle is None:
        return None
    stored = {d.key: (d, obs) for d, obs in repo.bundle_series(conn, row["id"], bundle)}
    if not set(REQUIRED) <= stored.keys():
        return None
    metrics = {k: metric(d, obs) for k, (d, obs) in stored.items() if obs}
    retail = metrics["ect.m.sa.retail.value"]
    vintage = repo.bundle_vintage(conn, retail.series_key, row["id"], bundle)

    def evidence(key, period=None):
        m = metrics[key]
        p = period or m.period
        value = next(o.value for o in stored[key][1] if o.period == p)
        return Evidence(series_key=key, period=p, value=value, release_key=row["release_key"])

    executive = []
    for group in ("retail", "core", "total"):
        k = f"ect.m.sa.{group}.value"
        m = metrics[k]
        c = m.change_prior
        if c and c.percent is not None:
            executive.append(
                Insight(
                    id=group,
                    kind="observation",
                    text=f"{m.label}: {m.value:,.1f} NZD million in {m.period_label}; "
                    f"{c.percent:+.1f}% ({c.absolute:+,.1f} NZD million) {c.label}.",
                    evidence=[evidence(k), evidence(k, c.comparison_period)],
                )
            )
    industry_changes = []
    for industry, label in INDUSTRIES.values():
        k = f"ect.m.sa.{industry}.value"
        m = metrics.get(k)
        if m and m.change_prior and m.change_prior.percent is not None:
            industry_changes.append((m.change_prior.percent, label, k))
    if industry_changes:
        low, high = min(industry_changes), max(industry_changes)
        executive.append(
            Insight(
                id="industry",
                kind="observation",
                text=f"Strongest industry movement: {high[1]} ({high[0]:+.1f}%); "
                f"weakest movement: {low[1]} ({low[0]:+.1f}%). Seasonally adjusted, monthly.",
                evidence=[
                    evidence(k, p)
                    for k in (high[2], low[2])
                    for p in (metrics[k].period, metrics[k].change_prior.comparison_period)
                ],
            )
        )
    total = metrics["ect.m.actual.total.value"]
    count = metrics["ect.m.actual.total.count"]
    avg = metrics["ect.m.actual.total.average"]
    executive.append(
        Insight(
            id="actual",
            kind="observation",
            text=f"Actual total spending was ${total.value / 1000:.2f} billion across {count.value / 1_000_000:.1f} "
            f"million transactions; the published mean was ${avg.value:.1f}. These are unadjusted measures.",
            evidence=[evidence(m.series_key) for m in (total, count, avg)],
        )
    )
    for group in ("retail", "core"):
        k = f"ect.q.sa.{group}.value"
        m = metrics.get(k)
        if m and m.change_prior:
            executive.append(
                Insight(
                    id="quarter-" + group,
                    kind="observation",
                    text=f"{m.label}, {m.period_label}: {m.change_prior.percent:+.1f}% versus the previous quarter.",
                    evidence=[evidence(k), evidence(k, m.change_prior.comparison_period)],
                )
            )
    values = [o.value for o in stored[retail.series_key][1]]
    trend = metrics["ect.m.trend.retail.value"]
    context = [
        Insight(
            id="history",
            kind="observation",
            text=f"Retail seasonally adjusted spending is {retail.value:,.1f} NZD million; "
            f"the captured history has {len(values)} monthly observations with a range of "
            f"{min(values):,.1f}–{max(values):,.1f} NZD million. Nominal comparisons include price changes.",
            evidence=[
                evidence(retail.series_key, o.period)
                for o in stored[retail.series_key][1]
                if o.value in (min(values), max(values), retail.value)
            ],
        ),
        Insight(
            id="trend",
            kind="observation",
            text=f"Retail trend spending: {trend.value:,.1f} NZD million"
            + (
                f", {trend.change_prior.percent:+.1f}% versus the previous month."
                if trend.change_prior
                else "."
            ),
            evidence=[evidence(trend.series_key)]
            + (
                [evidence(trend.series_key, trend.change_prior.comparison_period)]
                if trend.change_prior
                else []
            ),
        ),
    ]
    previous = repo.previous_vintage(conn, retail.series_key, row["published_at"])
    rev = (
        revision_view(
            conn,
            retail.series_key,
            base_release_key=previous.release_key,
            compare_release_key=row["release_key"],
        )
        if previous
        else None
    )
    available = bool(rev and rev.base and rev.compare)
    note = (
        rev.coverage.note
        if rev
        else "No earlier publication is stored for this series, so revisions and changes since "
        "the previous release cannot be assessed."
    )
    revisions = RevisionBlock(
        available=available,
        note=note,
        series_key=retail.series_key,
        against_title=rev.base.title if available else None,
        n_common=rev.n_common if available else 0,
        n_revised=rev.n_revised if available else 0,
        mean_abs=(
            sum(abs(r.absolute) for r in rev.rows) / rev.n_common
            if available and rev.n_common
            else None
        ),
        largest=sorted(rev.rows, key=lambda r: abs(r.absolute), reverse=True)[:8]
        if available
        else [],
    )
    decomposition = []
    if available:
        points = repo.vintage_points(conn, previous.vintage_id) if previous else {}
        if points:
            p = max(points)
            current = {o.period: o.value for o in stored[retail.series_key][1]}
            if p in current:
                decomposition = [
                    Decomposition(
                        label=retail.label,
                        series_key=retail.series_key,
                        previous_release_title=previous.title,
                        previous_period=p,
                        previous_published_value=points[p].value,
                        same_period_now=current[p],
                        new_period=retail.period,
                        new_value=retail.value,
                        revision_component=current[p] - points[p].value,
                        new_period_component=retail.value - current[p],
                        total_change=retail.value - points[p].value,
                    )
                ]
    summary = release_summary(conn, row, analysable_slugs={SLUG})
    analysis = ReleaseAnalysis(
        release=summary,
        executive_summary=executive,
        headline_metrics=[
            metrics[k]
            for k in (
                "ect.m.sa.retail.value",
                "ect.m.sa.core.value",
                "ect.m.sa.total.value",
                "ect.m.actual.total.value",
                "ect.m.actual.total.count",
                "ect.m.actual.total.average",
            )
        ],
        context=context,
        previous_comparison=PreviousComparison(
            available=bool(decomposition),
            note=note,
            previous_release_title=revisions.against_title,
            decompositions=decomposition,
        ),
        revisions=revisions,
        corrections=_corrections(conn, row["id"], bundle, vintage, primary_key=retail.series_key),
        interpretation=[],
        methodology=Methodology(
            definitions=CAVEATS[:4], notes=CAVEATS[4:], source_url=row["page_url"]
        ),
        vintage_captured_at=to_akl_iso(vintage.captured_at),
    )
    series = []
    for key, (d, observations) in stored.items():
        v = repo.bundle_vintage(conn, key, row["id"], bundle)
        meta = repo.get_series_row(conn, key, v.vintage_id)
        series.append(
            SeriesDataOut(
                series=series_out(
                    meta, len(repo.list_vintages(conn, key)), max(o.period for o in observations)
                ),
                vintage=vintage_out(conn, v),
                points=[
                    PointOut(
                        period=o.period,
                        value=o.value,
                        status=o.status.value,
                        std_error=o.std_error,
                        released_in=o.released_in,
                    )
                    for o in observations
                ],
                source_url=d.source_url,
                caveat=" ".join(CAVEATS[1:3]),
            )
        )
    return EctDashboardOut(analysis=analysis, series=series)

"""Evidence-grounded GDP release analysis and dashboard.

Growth rates are Stats NZ's published percentages (1 d.p.), reconciled with the levels at ingestion. Quarterly growth,
the annual change of a quarter and annual average growth are three different measures: every metric, sentence and
series names which one it is. Revisions are expected in national accounts and are shown, never smoothed over.
"""

from __future__ import annotations

import sqlite3
from statistics import mean

from nzstats.adapters.gdp.series import HEADLINE, KEYS, SLUG
from nzstats.clock import to_akl_iso
from nzstats.insights.migration import _corrections
from nzstats.insights.summary import release_summary
from nzstats.models import (
    ChangeOut,
    Evidence,
    GdpDashboardOut,
    GdpRevisionRow,
    GdpRevisionTable,
    GdpSeriesOut,
    Insight,
    Methodology,
    Metric,
    PointOut,
    PreviousComparison,
    ReleaseAnalysis,
    RevisionBlock,
    RevisionRowOut,
)
from nzstats.stats.gdp import round_1dp
from nzstats.stats.periods import add_months, month_label
from nzstats.store import repo

QOQ = "gdp.production.cv.sa.pct_qoq"
YOY = "gdp.production.cv.sa.pct_yoy"
AVG = "gdp.production.cv.nsa.pct_annual_avg"
EXP_QOQ = "gdp.expenditure.cv.sa.pct_qoq"
PER_CAPITA = "gdp.per_capita.production.cv.sa"
NOMINAL = "gdp.expenditure.cp.sa"
REVISION_QUARTERS = 8
CAVEATS = [
    "Gross domestic product (GDP) measures the value of goods and services produced in New Zealand. Stats NZ's "
    "headline is the production measure in chain-volume terms (real, 2009/10 prices), seasonally adjusted.",
    "Three growth measures are shown and are never interchangeable: quarterly growth compares a quarter with the "
    "previous quarter (seasonally adjusted); the annual change of a quarter compares it with the same quarter a "
    "year earlier (seasonally adjusted); annual average growth compares the four quarters to date with the four "
    "before them (actual values). Stats NZ's release page calls the last one 'Annual growth'.",
    "Chain-volume (real) values remove the effect of price changes; current-price (nominal) values do not. "
    "Seasonally adjusted and actual values are different series. They are kept on separate charts.",
    "The production and expenditure measures are estimated independently from different data and usually "
    "differ; neither is a correction of the other.",
    "National accounts are revised as more complete information arrives, and seasonal adjustment re-estimates "
    "history every quarter. The first-published and latest figures for a quarter can differ.",
    "Per-person values divide GDP by Stats NZ's population estimate. Stats NZ's file declares an inconsistent "
    "magnitude for some per-capita series; values are shown in dollars as published.",
    "This page describes published statistics only. It makes no forecast and no statement about policy.",
]
_MEASURE = {
    "pct_qoq": "quarterly_change",
    "pct_yoy": "annual_change",
    "pct_annual_avg": "annual_average_change",
}


def _quarter(period: str) -> str:
    return f"{month_label(period)} quarter"


def _describe(key: str) -> tuple[str, str, str, bool]:
    """(measure, approach, price basis, per capita) from a GDP series key."""
    parts = key.split(".")[1:]
    per_capita = parts[0] == "per_capita"
    if per_capita:
        parts = parts[1:]
    approach, basis = parts[0], parts[1]
    measure = _MEASURE.get(parts[3], "level") if len(parts) > 3 else "level"
    return measure, approach, "chain_volume" if basis == "cv" else "current_prices", per_capita


def _latest_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT r.* FROM release r WHERE r.series_slug=? AND EXISTS "
        "(SELECT 1 FROM vintage v WHERE v.release_id=r.id) ORDER BY r.published_at DESC LIMIT 1",
        (SLUG,),
    ).fetchone()


def _load(conn: sqlite3.Connection, release_id: int | None):
    row = _latest_row(conn) if release_id is None else repo.get_release_by_id(conn, release_id)
    if row is None or row["series_slug"] != SLUG:
        return None
    bundle = repo.release_bundle(conn, row["id"])
    if bundle is None:
        return None
    stored = {d.key: (d, obs) for d, obs in repo.bundle_series(conn, row["id"], bundle)}
    if not set(KEYS) <= stored.keys() or not all(stored[k][1] for k in KEYS):
        return None
    vintage = repo.bundle_vintage(conn, HEADLINE, row["id"], bundle)
    captured = repo.bundle_captured_at(conn, row["id"], bundle)
    return (row, bundle, stored, vintage, captured) if vintage and captured else None


def _values(stored, key: str) -> dict[str, float]:
    return {o.period: o.value for o in stored[key][1]}


def _change(v: float) -> str:
    return f"rose {v:.1f}%" if v > 0 else f"fell {abs(v):.1f}%" if v < 0 else "was unchanged (0.0%)"


def _metric(stored, key: str) -> Metric:
    d, obs = stored[key]
    values = _values(stored, key)
    ref = max(values)

    def compare(lag: int) -> ChangeOut | None:
        period = add_months(ref, -lag)
        if period not in values:
            return None
        return ChangeOut(
            label=f"vs {_quarter(period)}" + (" (a year earlier)" if lag == 12 else ""),
            comparison_period=period,
            previous=values[period],
            absolute=round(
                values[ref] - values[period], 1
            ),  # percentage points between published rates
            percent=None,
        )

    return Metric(
        series_key=key,
        label=d.name,
        value=values[ref],
        unit="percent",
        frequency="quarterly",
        period=ref,
        period_label=f"Quarter ended {month_label(ref)}",
        status=next(o.status.value for o in obs if o.period == ref),
        std_error=None,
        change_prior=compare(3),
        change_year_ago=compare(12),
    )


def _evidence(row, stored, key: str, period: str) -> Evidence:
    return Evidence(
        series_key=key,
        period=period,
        value=_values(stored, key)[period],
        release_key=row["release_key"],
    )


def _insights(row, stored, ref: str) -> tuple[list[Insight], list[Insight]]:
    q, a, y = _values(stored, QOQ), _values(stored, AVG), _values(stored, YOY)
    prior, year = add_months(ref, -3), add_months(ref, -12)
    ev = lambda key, period: _evidence(row, stored, key, period)  # noqa: E731
    text = f"Real GDP (production measure, seasonally adjusted) {_change(q[ref])} in the {_quarter(ref)}"
    evidence = [ev(QOQ, ref)]
    if prior in q:
        text += f", after {q[prior]:.1f}% in the {_quarter(prior)}"
        evidence.append(ev(QOQ, prior))
    executive = [Insight(id="quarterly", kind="observation", text=text + ".", evidence=evidence)]
    direction = "higher" if a[ref] >= 0 else "lower"
    executive.append(
        Insight(
            id="annual_average",
            kind="observation",
            text=f"In the year ended {month_label(ref)}, real GDP was {abs(a[ref]):.1f}% {direction} than in the "
            f"year ended {month_label(year)} (annual average growth, from actual values).",
            evidence=[ev(AVG, ref)],
        )
    )
    direction = "higher" if y[ref] >= 0 else "lower"
    executive.append(
        Insight(
            id="annual_change",
            kind="observation",
            text=f"Seasonally adjusted real GDP in the {_quarter(ref)} was {abs(y[ref]):.1f}% {direction} than in "
            f"the {_quarter(year)}. This compares one quarter with the same quarter a year earlier; it is not "
            "annual average growth.",
            evidence=[ev(YOY, ref)],
        )
    )
    context = []
    e = _values(stored, EXP_QOQ)
    context.append(
        Insight(
            id="expenditure",
            kind="observation",
            text=f"The expenditure measure of real GDP (seasonally adjusted) {_change(e[ref])} in the quarter. "
            "The production and expenditure measures are estimated independently and usually differ.",
            evidence=[ev(EXP_QOQ, ref)],
        )
    )
    pc = _values(stored, PER_CAPITA)
    if prior in pc:
        change = (pc[ref] / pc[prior] - 1) * 100
        context.append(
            Insight(
                id="per_capita",
                kind="observation",
                text=f"Real GDP per person (production, seasonally adjusted) was ${pc[ref]:,.0f} in the "
                f"{_quarter(ref)}, against ${pc[prior]:,.0f} in the {_quarter(prior)} "
                f"({round_1dp(change):+.1f}%, calculated here from the two published values).",
                evidence=[ev(PER_CAPITA, ref), ev(PER_CAPITA, prior)],
            )
        )
    nominal = _values(stored, NOMINAL)
    context.append(
        Insight(
            id="nominal",
            kind="observation",
            text=f"Nominal GDP (expenditure measure, current prices, seasonally adjusted) was "
            f"${nominal[ref] / 1000:,.1f} billion in the quarter. Nominal values include price changes.",
            evidence=[ev(NOMINAL, ref)],
        )
    )
    return executive, context


def _revision_block(conn, row, stored) -> RevisionBlock:
    previous = repo.previous_vintage(conn, QOQ, row["published_at"])
    if previous is None:
        return RevisionBlock(
            available=False,
            note="No earlier GDP release is stored, so revisions to published quarterly growth cannot be assessed.",
            series_key=QOQ,
            against_title=None,
            n_common=0,
            n_revised=0,
            mean_abs=None,
            largest=[],
        )
    old = repo.vintage_points(conn, previous.vintage_id)
    new = {o.period: o for o in stored[QOQ][1]}
    diffs = [(p, old[p], new[p]) for p in sorted(set(old) & set(new))]
    revised = [(p, o, n) for p, o, n in diffs if abs(n.value - o.value) > 1e-9]
    largest = sorted(revised, key=lambda t: (abs(t[2].value - t[1].value), t[0]), reverse=True)[:8]
    return RevisionBlock(
        available=True,
        note=f"{len(revised)} of {len(diffs)} quarters of published quarterly growth shared with {previous.title} "
        "were revised. National accounts are revised as more complete information arrives.",
        series_key=QOQ,
        against_title=previous.title,
        n_common=len(diffs),
        n_revised=len(revised),
        mean_abs=mean(abs(n.value - o.value) for _, o, n in diffs) if diffs else None,
        largest=[
            RevisionRowOut(
                period=p,
                original=o.value,
                revised=n.value,
                absolute=round(n.value - o.value, 1),
                percent=None,  # a percentage change of a growth rate is not meaningful
                original_status=o.status.value,
                revised_status=n.status.value,
            )
            for p, o, n in largest
        ],
    )


def _first_published(
    conn, key: str, published_at: str
) -> list[tuple[str, str | None, dict[str, float]]]:
    """Each stored release up to `published_at`, oldest first, with its first stored values of `key`."""
    references = dict(
        conn.execute(
            "SELECT release_key, reference_period FROM release WHERE series_slug = ?", (SLUG,)
        ).fetchall()
    )
    seen: dict[str, tuple[str, str | None, dict[str, float]]] = {}
    # Activation changes when a bundle is restored; ids retain the original insertion order.
    vintages = sorted(repo.list_vintages(conn, key), key=lambda v: (v.published_at, v.vintage_id))
    for v in vintages:
        if v.published_at > published_at or v.release_key in seen:
            continue  # later releases cannot be "first published" for this view; keep each release's original
        points = {p: pt.value for p, pt in repo.vintage_points(conn, v.vintage_id).items()}
        seen[v.release_key] = (v.title, references.get(v.release_key), points)
    return list(seen.values())


def _revision_table(conn, row, stored, key: str) -> GdpRevisionTable:
    d = stored[key][0]
    releases = _first_published(conn, key, row["published_at"])
    if len(releases) < 2:
        return GdpRevisionTable(
            series_key=key,
            label=d.name,
            available=False,
            note="Only one GDP release is stored, so first-published and latest figures cannot be compared.",
            rows=[],
        )
    latest = _values(stored, key)
    ref = max(latest)
    rows = []
    for period in (add_months(ref, -3 * k) for k in range(REVISION_QUARTERS)):
        if period not in latest:
            continue
        own = next((r for r in releases if r[1] == period and period in r[2]), None)
        first = own or next((r for r in releases if period in r[2]), None)
        if first is None:
            continue
        rows.append(
            GdpRevisionRow(
                period=period,
                first_value=first[2][period],
                first_release=first[0],
                first_is_publication=own is not None,
                latest_value=latest[period],
                latest_release=row["title"],
                revision=round_1dp(latest[period] - first[2][period]),
            )
        )
    return GdpRevisionTable(
        series_key=key,
        label=d.name,
        available=True,
        note="First published: the figure in the release for that quarter. Where that release is not stored, the "
        f"earliest stored figure is shown and marked as earliest stored. Latest: {row['title']}.",
        rows=rows,
    )


def _build(
    conn: sqlite3.Connection, release_id: int | None, *, full: bool
) -> GdpDashboardOut | None:
    loaded = _load(conn, release_id)
    if loaded is None:
        return None
    row, bundle, stored, vintage, captured = loaded
    ref = max(_values(stored, HEADLINE))
    executive, context = _insights(row, stored, ref)
    revisions = _revision_block(conn, row, stored)
    analysis = ReleaseAnalysis(
        release=release_summary(conn, row, analysable_slugs={SLUG}),
        executive_summary=executive,
        headline_metrics=[_metric(stored, k) for k in (QOQ, AVG, YOY)],
        context=context,
        previous_comparison=PreviousComparison(
            available=False,
            note="GDP growth is compared with earlier publications in the revisions table.",
            previous_release_title=revisions.against_title,
            decompositions=[],
        ),
        revisions=revisions,
        corrections=_corrections(conn, row["id"], bundle, vintage, primary_key=HEADLINE),
        interpretation=[],
        methodology=Methodology(
            definitions=CAVEATS[:3], notes=CAVEATS[3:], source_url=row["page_url"]
        ),
        vintage_captured_at=to_akl_iso(captured),
    )
    series = []
    if full:
        for key in KEYS:
            d, obs = stored[key]
            measure, approach, basis, per_capita = _describe(key)
            series.append(
                GdpSeriesOut(
                    key=key,
                    name=d.name,
                    unit=d.unit,
                    measure=measure,
                    approach=approach,
                    price_basis=basis,
                    adjustment=d.adjustment.value,
                    per_capita=per_capita,
                    definition=d.definition,
                    points=[
                        PointOut(
                            period=o.period,
                            value=o.value,
                            status=o.status.value,
                            std_error=None,
                            released_in=None,
                        )
                        for o in obs
                    ],
                    source_url=d.source_url,
                )
            )
    return GdpDashboardOut(
        analysis=analysis,
        reference_period=ref,
        published_at=to_akl_iso(row["published_at"]),
        captured_at=to_akl_iso(captured),
        series=series,
        revisions=[_revision_table(conn, row, stored, k) for k in (QOQ, AVG)] if full else [],
        sources=sorted(
            {d.source_url for d, _ in stored.values() if d.source_url}
            | {row["page_url"] or ""} - {""}
        ),
        caveats=CAVEATS,
    )


def build_gdp_analysis(
    conn: sqlite3.Connection, release_id: int | None = None
) -> ReleaseAnalysis | None:
    result = _build(conn, release_id, full=False)
    return result.analysis if result else None


def build_gdp_dashboard(
    conn: sqlite3.Connection, release_id: int | None = None
) -> GdpDashboardOut | None:
    return _build(conn, release_id, full=True)

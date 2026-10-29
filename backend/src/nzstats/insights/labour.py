"""Evidence-grounded labour market release analysis and dashboard (HLFS headline rates and the LCI).

Rates and changes are Stats NZ's published figures; the HLFS identities and LCI changes are checked at ingestion.
The previous quarter's rate is the figure as revised in this release, and the sentence says when it was first
published differently. HLFS, LCI and QES are different surveys and are never combined.
"""

from __future__ import annotations

import sqlite3

from nzstats.adapters.labour.series import KEYS, SLUG, UNEMPLOYMENT
from nzstats.clock import to_akl_iso
from nzstats.insights.migration import _corrections
from nzstats.insights.summary import release_summary
from nzstats.insights.vintages import first_latest_table, first_stored
from nzstats.models import (
    ChangeOut,
    Evidence,
    Insight,
    Kpi,
    LabourDashboardOut,
    LabourSeriesOut,
    Methodology,
    Metric,
    PointOut,
    PreviousComparison,
    ReleaseAnalysis,
    RevisionBlock,
    RevisionRowOut,
)
from nzstats.stats.periods import add_months, month_label
from nzstats.store import repo

EMPLOYMENT, PARTICIPATION = "hlfs.rate.employment.sa", "hlfs.rate.participation.sa"
UNDERUTILISATION = "hlfs.rate.underutilisation.sa"
EMPLOYED, UNEMPLOYED = "hlfs.level.employed.sa", "hlfs.level.unemployed.sa"
LCI_QOQ, LCI_YOY = "lci.all_wages.pct_qoq", "lci.all_wages.pct_yoy"
HEADLINE_KEYS = (UNEMPLOYMENT, EMPLOYMENT, PARTICIPATION, UNDERUTILISATION, LCI_YOY)
CAVEATS = [
    "The Household Labour Force Survey (HLFS) is a sample survey: its estimates have sampling error, and small "
    "quarterly movements may not be statistically significant. Stats NZ publishes sampling errors with each release.",
    "The unemployment rate is unemployed people as a share of the labour force; the employment rate and the "
    "participation rate are shares of the working-age population (people aged 15 and over). The underutilisation "
    "rate is broader: it also counts people who want more hours and people who could work but are not looking or "
    "not yet available, as a share of the extended labour force.",
    "HLFS rates are seasonally adjusted and re-estimated every quarter, so earlier quarters can be revised. Where "
    "an earlier release is stored, the first-published figure is shown next to the latest.",
    "The Labour Cost Index (LCI) measures changes in salary and wage rates for the same work of the same quality. "
    "The Quarterly Employment Survey (QES) measures average earnings, which also change with the mix of jobs and "
    "hours. They are different surveys and are not combined here; QES figures are not shown.",
    "HLFS levels are published in thousands and rates to one decimal place.",
    "This page describes published statistics only. It makes no forecast and no statement about policy.",
]
_MEASURE = {
    "rate": "rate",
    "level": "level",
    "index": "index",
    "pct_qoq": "quarterly_change",
    "pct_yoy": "annual_change",
}


def _quarter(period: str) -> str:
    return f"{month_label(period)} quarter"


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
    vintage = repo.bundle_vintage(conn, UNEMPLOYMENT, row["id"], bundle)
    captured = repo.bundle_captured_at(conn, row["id"], bundle)
    return (row, bundle, stored, vintage, captured) if vintage and captured else None


def _values(stored, key: str) -> dict[str, float]:
    return {o.period: o.value for o in stored[key][1]}


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


def build_labour_overview_kpi(conn: sqlite3.Connection) -> tuple[Kpi, str] | None:
    loaded = _load(conn, None)
    if loaded is None:
        return None
    row, _, stored, _, captured = loaded
    return (
        Kpi(
            metric=_metric(stored, UNEMPLOYMENT),
            release_id=row["id"],
            published_at=to_akl_iso(row["published_at"]),
            source_url=row["page_url"],
        ),
        to_akl_iso(captured),
    )


def _first_published(conn, row, key: str, period: str) -> float | None:
    """The value of `period` in its own release, when that release is stored and earlier than this one."""
    for release in first_stored(conn, SLUG, key, row["published_at"]):
        if release.reference_period == period and release.title != row["title"]:
            return release.values.get(period)
    return None


def _insights(conn, row, stored, ref: str) -> tuple[list[Insight], list[Insight]]:
    def ev(key: str, period: str) -> Evidence:
        return Evidence(
            series_key=key,
            period=period,
            value=_values(stored, key)[period],
            release_key=row["release_key"],
        )

    rate = _values(stored, UNEMPLOYMENT)
    prior = add_months(ref, -3)
    text = f"The unemployment rate (HLFS, seasonally adjusted) was {rate[ref]:.1f}% in the {_quarter(ref)}"
    evidence = [ev(UNEMPLOYMENT, ref)]
    if prior in rate:
        word = (
            "up from"
            if rate[ref] > rate[prior]
            else "down from"
            if rate[ref] < rate[prior]
            else "unchanged from"
        )
        text += f", {word} {rate[prior]:.1f}% in the {_quarter(prior)}"
        evidence.append(ev(UNEMPLOYMENT, prior))
        first = _first_published(conn, row, UNEMPLOYMENT, prior)
        if first is not None and abs(first - rate[prior]) > 1e-9:
            text += f" (as revised in this release; first published as {first:.1f}%)"
    executive = [Insight(id="unemployment", kind="observation", text=text + ".", evidence=evidence)]
    er, pr = _values(stored, EMPLOYMENT), _values(stored, PARTICIPATION)
    employed, unemployed = _values(stored, EMPLOYED), _values(stored, UNEMPLOYED)
    executive.append(
        Insight(
            id="employment",
            kind="observation",
            text=f"The employment rate was {er[ref]:.1f}% and the labour force participation rate {pr[ref]:.1f}% "
            f"(seasonally adjusted). {employed[ref] * 1000:,.0f} people were employed and "
            f"{unemployed[ref] * 1000:,.0f} were unemployed.",
            evidence=[
                ev(EMPLOYMENT, ref),
                ev(PARTICIPATION, ref),
                ev(EMPLOYED, ref),
                ev(UNEMPLOYED, ref),
            ],
        )
    )
    under = _values(stored, UNDERUTILISATION)
    executive.append(
        Insight(
            id="underutilisation",
            kind="observation",
            text=f"The underutilisation rate, a broader measure than unemployment, was {under[ref]:.1f}%.",
            evidence=[ev(UNDERUTILISATION, ref)],
        )
    )
    context = []
    q, y = _values(stored, LCI_QOQ), _values(stored, LCI_YOY)
    if ref in q and ref in y:
        context.append(
            Insight(
                id="lci",
                kind="observation",
                text=f"Salary and wage rates (Labour Cost Index, all sectors) rose {q[ref]:.1f}% in the quarter and "
                f"{y[ref]:.1f}% over the year to the {_quarter(ref)}. The LCI measures the price of labour for the "
                "same job; it is not average earnings.",
                evidence=[ev(LCI_QOQ, ref), ev(LCI_YOY, ref)],
            )
        )
    return executive, context


def _revision_block(conn, row, stored) -> RevisionBlock:
    previous = repo.previous_vintage(conn, UNEMPLOYMENT, row["published_at"])
    if previous is None:
        return RevisionBlock(
            available=False,
            note="No earlier labour market release is stored, so revisions to the unemployment rate cannot be "
            "assessed.",
            series_key=UNEMPLOYMENT,
            against_title=None,
            n_common=0,
            n_revised=0,
            mean_abs=None,
            largest=[],
        )
    old = repo.vintage_points(conn, previous.vintage_id)
    new = {o.period: o for o in stored[UNEMPLOYMENT][1]}
    diffs = [(p, old[p], new[p]) for p in sorted(set(old) & set(new))]
    revised = [(p, o, n) for p, o, n in diffs if abs(n.value - o.value) > 1e-9]
    largest = sorted(revised, key=lambda t: (abs(t[2].value - t[1].value), t[0]), reverse=True)[:8]
    return RevisionBlock(
        available=True,
        note=f"{len(revised)} of {len(diffs)} quarters of the seasonally adjusted unemployment rate shared with "
        f"{previous.title} were revised. Seasonal adjustment re-estimates history every quarter.",
        series_key=UNEMPLOYMENT,
        against_title=previous.title,
        n_common=len(diffs),
        n_revised=len(revised),
        mean_abs=sum(abs(n.value - o.value) for _, o, n in diffs) / len(diffs) if diffs else None,
        largest=[
            RevisionRowOut(
                period=p,
                original=o.value,
                revised=n.value,
                absolute=round(n.value - o.value, 1),
                percent=None,
                original_status=o.status.value,
                revised_status=n.status.value,
            )
            for p, o, n in largest
        ],
    )


def _build(
    conn: sqlite3.Connection, release_id: int | None, *, full: bool
) -> LabourDashboardOut | None:
    loaded = _load(conn, release_id)
    if loaded is None:
        return None
    row, bundle, stored, vintage, captured = loaded
    ref = max(_values(stored, UNEMPLOYMENT))
    executive, context = _insights(conn, row, stored, ref)
    revisions = _revision_block(conn, row, stored)
    analysis = ReleaseAnalysis(
        release=release_summary(conn, row, analysable_slugs={SLUG}),
        executive_summary=executive,
        headline_metrics=[_metric(stored, k) for k in HEADLINE_KEYS],
        context=context,
        previous_comparison=PreviousComparison(
            available=False,
            note="Rates are compared with earlier publications in the revisions table.",
            previous_release_title=revisions.against_title,
            decompositions=[],
        ),
        revisions=revisions,
        corrections=_corrections(conn, row["id"], bundle, vintage, primary_key=UNEMPLOYMENT),
        interpretation=[],
        methodology=Methodology(
            definitions=CAVEATS[:2], notes=CAVEATS[2:], source_url=row["page_url"]
        ),
        vintage_captured_at=to_akl_iso(captured),
    )
    series = []
    if full:
        for key in KEYS:
            d, obs = stored[key]
            parts = key.split(".")  # hlfs.<rate|level>.<name>.sa or lci.all_wages.<index|pct_*>
            survey, kind = parts[0], parts[-1] if parts[0] == "lci" else parts[1]
            series.append(
                LabourSeriesOut(
                    key=key,
                    name=d.name,
                    unit=d.unit,
                    survey=survey,
                    measure=_MEASURE[kind],
                    adjustment=d.adjustment.value,
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
    return LabourDashboardOut(
        analysis=analysis,
        reference_period=ref,
        published_at=to_akl_iso(row["published_at"]),
        captured_at=to_akl_iso(captured),
        series=series,
        revisions=[
            first_latest_table(
                conn,
                SLUG,
                row,
                UNEMPLOYMENT,
                stored[UNEMPLOYMENT][0].name,
                _values(stored, UNEMPLOYMENT),
            )
        ]
        if full
        else [],
        sources=sorted(
            {d.source_url for d, _ in stored.values() if d.source_url}
            | {row["page_url"] or ""} - {""}
        ),
        caveats=CAVEATS,
    )


def build_labour_analysis(
    conn: sqlite3.Connection, release_id: int | None = None
) -> ReleaseAnalysis | None:
    result = _build(conn, release_id, full=False)
    return result.analysis if result else None


def build_labour_dashboard(
    conn: sqlite3.Connection, release_id: int | None = None
) -> LabourDashboardOut | None:
    return _build(conn, release_id, full=True)

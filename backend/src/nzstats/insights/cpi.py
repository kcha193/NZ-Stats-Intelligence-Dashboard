"""Evidence-grounded CPI release analysis and a single-bundle dashboard projection.

Percentage changes are derived here from the published (rounded) index numbers, as Stats NZ's
official changes are. Group contributions are Stats NZ's published percentage-point figures and are
never estimated. A percentage change, a percentage-point contribution and a share of the total
movement are different measures and are kept apart in every model.
"""

from __future__ import annotations

import sqlite3
from decimal import ROUND_HALF_UP, Decimal
from statistics import mean

from nzstats.adapters.cpi.adapter import SA_REVISION_MATERIALITY
from nzstats.adapters.cpi.series import (
    BASE_TEXT,
    CORE_KEYS,
    LEVEL1,
    LEVEL1_SLUGS,
    SLUG,
    classification,
    contribution_key,
    source_reference,
)
from nzstats.clock import to_akl_iso
from nzstats.insights.migration import _corrections
from nzstats.insights.summary import release_summary
from nzstats.models import (
    ChangeOut,
    CpiContributionBlock,
    CpiContributionItem,
    CpiDashboardOut,
    CpiPoint,
    CpiSeriesOut,
    CpiUnderlyingOut,
    Decomposition,
    Evidence,
    Insight,
    Kpi,
    Methodology,
    Metric,
    PointOut,
    PreviousComparison,
    ReleaseAnalysis,
    RevisionBlock,
    RevisionRowOut,
)
from nzstats.stats.cpi import annual_changes, quarterly_changes
from nzstats.stats.periods import add_months, month_label
from nzstats.store import repo

ALL = "cpi.index.nsa.all_groups"
CAVEATS = [
    "The consumers price index (CPI) measures the change in prices of a fixed basket of goods and "
    "services bought by New Zealand households. It is not a cost-of-living index for any one household.",
    f"Index numbers use a {BASE_TEXT} base. Quarterly change compares a quarter with the previous "
    "quarter; annual change compares it with the same quarter a year earlier. They are different "
    "measures and are never drawn as one series. Official changes are calculated from the rounded "
    "published index numbers, as here.",
    "Tradables are goods and services exposed to foreign competition; non-tradables are not. "
    "Non-tradables inflation is not core inflation.",
    "A group's percentage price change, its percentage-point contribution to the headline change and "
    "its share of the total movement are three different measures. Contributions shown are the "
    "percentage-point figures Stats NZ publishes (supplementary analytical information calculated "
    "from unrounded index numbers), so the 11 groups sum to the headline change only approximately.",
    "Seasonally adjusted series are re-estimated every quarter and can be revised. Unadjusted CPI is "
    "not normally revised.",
    "Stats NZ updates the basket and expenditure weights periodically and describes method changes in "
    "its price index methods updates. For the September 2026 quarter these include administrative "
    "data for long-distance bus fares. Stats NZ has also noted that a timing error in vehicle "
    "relicensing fees (a January 2025 increase applied as a catch-up in June 2025) raised annual "
    "inflation in the March 2026 quarter relative to when the change occurred.",
    "Selected Price Indexes are a separate monthly release and are not monthly CPI. Quarterly CPI "
    "remains the official measure. Trimmed means and weighted percentiles shown are official "
    "Stats NZ measures from the release workbook; this dashboard does not define core inflation.",
    "This page describes published statistics only. It makes no forecast and no statement about "
    "policy decisions.",
]
GROUP_NAME = {slug: name for _, slug, name in LEVEL1}
ORDER = ("all_groups", "tradables", "non_tradables", *LEVEL1_SLUGS)


def _verb(value: float) -> str:
    return "was unchanged" if round(value, 1) == 0 else "rose" if value > 0 else "fell"


def _headline_text(q: float, a: float, ref: str, level: float) -> str:
    def phrase(value: float, where: str, *, verb: bool) -> str:
        if round(value, 1) == 0:
            return f"was unchanged {where}"
        return (f"{_verb(value)} " if verb else "") + f"{abs(value):.1f}% {where}"

    same = _verb(q) == _verb(a) and round(q, 1) != 0
    return (
        f"The consumers price index (CPI) {phrase(q, f'in the {_quarter(ref)}', verb=True)} and "
        f"{phrase(a, f'over the 12 months to {month_label(ref)}', verb=not same)} "
        f"(index {level:,.0f}, {BASE_TEXT.replace('quarter (=', 'quarter = ').rstrip(')')})."
    )


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
    if not set(CORE_KEYS) <= stored.keys() or not all(stored[k][1] for k in CORE_KEYS):
        return None
    vintage = repo.bundle_vintage(conn, ALL, row["id"], bundle)
    return (row, bundle, stored, vintage) if vintage else None


def _levels(stored, key: str) -> dict[str, float]:
    return {o.period: o.value for o in stored[key][1]} if key in stored else {}


def _rate_metric(stored, slug: str, horizon: str, label: str) -> Metric:
    key = f"cpi.index.nsa.{slug}"
    levels = _levels(stored, key)
    rates = (annual_changes if horizon == "a" else quarterly_changes)(levels)
    ref = max(levels)

    def compare(lag: int, text: str) -> ChangeOut | None:
        period = add_months(ref, -lag)
        if period not in rates:
            return None
        return ChangeOut(
            label=f"vs {_quarter(period)}"
            if lag == 3
            else f"vs {_quarter(period)} (a year earlier)",
            comparison_period=period,
            previous=rates[period],
            absolute=rates[ref] - rates[period],  # percentage points: a change in a rate
            percent=None,
        )

    return Metric(
        series_key=key,
        label=label,
        value=rates[ref],
        unit="percent",
        frequency="quarterly",
        period=ref,
        period_label=f"Quarter ended {month_label(ref)}",
        status=next(o.status.value for o in stored[key][1] if o.period == ref),
        std_error=None,
        change_prior=compare(3, "prior"),
        change_year_ago=compare(12, "year"),
    )


def _headline_metrics(stored) -> list[Metric]:
    return [
        _rate_metric(stored, "all_groups", "a", "CPI annual inflation, all groups"),
        _rate_metric(stored, "all_groups", "q", "CPI quarterly inflation, all groups"),
        _rate_metric(stored, "tradables", "a", "Tradables annual inflation"),
        _rate_metric(stored, "non_tradables", "a", "Non-tradables annual inflation"),
    ]


def build_cpi_overview_kpi(conn: sqlite3.Connection) -> tuple[Kpi, str] | None:
    loaded = _load(conn, None)
    if loaded is None:
        return None
    row, _, stored, vintage = loaded
    return (
        Kpi(
            metric=_headline_metrics(stored)[0],
            release_id=row["id"],
            published_at=to_akl_iso(row["published_at"]),
            source_url=row["page_url"],
        ),
        to_akl_iso(vintage.captured_at),
    )


def _evidence(row, stored, key: str, period: str) -> Evidence:
    value = next(o.value for o in stored[key][1] if o.period == period)
    return Evidence(series_key=key, period=period, value=value, release_key=row["release_key"])


def _contributions(stored, ref: str, headline: dict[str, float]) -> list[CpiContributionBlock]:
    blocks = []
    for horizon, name in (("q", "quarterly"), ("a", "annual")):
        items = [
            (slug, stored[contribution_key(horizon, slug)][1][0].value)
            for slug in LEVEL1_SLUGS
            if contribution_key(horizon, slug) in stored
        ]
        if not items:
            blocks.append(
                CpiContributionBlock(
                    horizon=name,  # type: ignore[arg-type]
                    available=False,
                    reference_period=None,
                    unit="percentage points",
                    items=[],
                    sum_points=None,
                    headline_pct=None,
                    gap_points=None,
                    note="Group contributions were not published in this release; none are shown or estimated.",
                )
            )
            continue
        ordered = sorted(items, key=lambda i: (-i[1], i[0]))
        total = sum(v for _, v in items)
        head = headline.get(ref)
        blocks.append(
            CpiContributionBlock(
                horizon=name,  # type: ignore[arg-type]
                available=True,
                reference_period=ref,
                unit="percentage points",
                items=[
                    CpiContributionItem(slug=s, group=GROUP_NAME[s], points=v, rank=n)
                    for n, (s, v) in enumerate(ordered, 1)
                ],
                sum_points=total,
                headline_pct=head,
                gap_points=None if head is None else head - total,
                note=f"Percentage-point contributions as published by Stats NZ for the {_quarter(ref)}. "
                "They are supplementary figures calculated from unrounded index numbers, so the groups sum to "
                f"{total:.2f} against a headline change of {head:.2f}."
                if head is not None
                else "",
            )
        )
    return blocks


def _series_out(stored) -> list[CpiSeriesOut]:
    out = []
    for key, (d, obs) in stored.items():
        if not key.startswith("cpi.index."):
            continue
        slug = key.rsplit(".", 1)[1]
        levels = {o.period: o.value for o in obs}
        q, a = quarterly_changes(levels), annual_changes(levels)
        out.append(
            CpiSeriesOut(
                key=key,
                slug=slug,
                name=d.name,
                unit=d.unit,
                adjustment=d.adjustment.value,
                classification=classification(slug),
                source_reference=source_reference(key),
                status=obs[-1].status.value,
                points=[
                    CpiPoint(
                        period=o.period,
                        index=o.value,
                        quarterly_pct=q.get(o.period),
                        annual_pct=a.get(o.period),
                    )
                    for o in obs
                ],
                source_url=d.source_url,
            )
        )
    rank = {s: n for n, s in enumerate(ORDER)}
    return sorted(out, key=lambda s: (s.adjustment != "none", rank.get(s.slug, len(rank)), s.slug))


def _revisions(conn, row, stored) -> tuple[RevisionBlock, object | None]:
    key = "cpi.index.sa.all_groups"
    previous = repo.previous_vintage(conn, key, row["published_at"])
    if previous is None:
        return (
            RevisionBlock(
                available=False,
                note="No earlier publication is stored for this series, so revisions and changes since "
                "the previous release cannot be assessed.",
                series_key=key,
                against_title=None,
                n_common=0,
                n_revised=0,
                mean_abs=None,
                largest=[],
            ),
            None,
        )
    old = repo.vintage_points(conn, previous.vintage_id)
    new = {o.period: o for o in stored[key][1]}
    common = sorted(set(old) & set(new))
    diffs = [(p, old[p], new[p]) for p in common]
    material = [(p, o, n) for p, o, n in diffs if abs(n.value - o.value) > SA_REVISION_MATERIALITY]
    rows = [
        RevisionRowOut(
            period=p,
            original=o.value,
            revised=n.value,
            absolute=n.value - o.value,
            percent=(n.value - o.value) / o.value * 100,
            original_status=o.status.value,
            revised_status=n.status.value,
        )
        for p, o, n in sorted(material, key=lambda t: abs(t[2].value - t[1].value), reverse=True)[
            :8
        ]
    ]
    note = (
        f"Seasonally adjusted CPI is re-estimated each quarter. {len(material)} of {len(common)} quarters shared "
        f"with {previous.title} changed by more than {SA_REVISION_MATERIALITY:g} index points; "
        "unadjusted CPI values are not normally revised."
    )
    block = RevisionBlock(
        available=True,
        note=note,
        series_key=key,
        against_title=previous.title,
        n_common=len(common),
        n_revised=len(material),
        mean_abs=mean(abs(n.value - o.value) for _, o, n in diffs) if diffs else None,
        largest=rows,
    )
    return block, previous


def _pp(value: float) -> str:
    """Two decimals, rounding ties up like the chart labels (published 0.305 reads 0.31, not 0.30)."""
    return f"{Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def _drivers(row, stored, ref: str, blocks: list[CpiContributionBlock]) -> Insight:
    if not all(b.available for b in blocks):
        return Insight(
            id="drivers",
            kind="observation",
            text="Stats NZ did not publish group contributions with this release, so the groups that "
            "drove the movement are not ranked and no contribution is estimated.",
            evidence=[_evidence(row, stored, ALL, ref)],
        )
    q, a = blocks
    parts = []
    top = [i for i in q.items if round(i.points, 2) > 0][:2]
    if top:
        parts.append(
            "By Stats NZ's published contribution to the quarterly change, "
            + " and ".join(f"{i.group} ({_pp(i.points)} percentage points)" for i in top)
            + " contributed most"
        )
    down = [i for i in q.items if round(i.points, 2) < 0]
    if down:
        parts.append(
            "while "
            + " and ".join(f"{i.group} ({_pp(i.points)} percentage points)" for i in down)
            + " subtracted"
        )
    text = " ".join(parts) + "." if parts else "No group made a visible quarterly contribution."
    year_top = [i for i in a.items if round(i.points, 2) > 0][:2]
    if year_top:
        text += (
            " Over the year, "
            + " and ".join(f"{i.group} ({_pp(i.points)} percentage points)" for i in year_top)
            + " contributed most."
        )
    evidence = [
        Evidence(
            series_key=contribution_key(h, i.slug),
            period=ref,
            value=i.points,
            release_key=row["release_key"],
        )
        for h, block in (("q", q), ("a", a))
        for i in block.items[:2]
    ]
    return Insight(
        id="drivers",
        kind="observation",
        text=text,
        evidence=evidence,
        caveat=f"The 11 groups sum to {_pp(q.sum_points)} percentage points quarterly against a "
        f"headline change of {_pp(q.headline_pct)}; Stats NZ calculates contributions from unrounded indexes.",
    )


def _build(
    conn: sqlite3.Connection, release_id: int | None, *, full: bool
) -> CpiDashboardOut | None:
    loaded = _load(conn, release_id)
    if loaded is None:
        return None
    row, bundle, stored, vintage = loaded
    levels = _levels(stored, ALL)
    ref = max(levels)
    q, a = quarterly_changes(levels), annual_changes(levels)
    trad = _levels(stored, "cpi.index.nsa.tradables")
    non = _levels(stored, "cpi.index.nsa.non_tradables")
    metrics = _headline_metrics(stored)
    blocks = _contributions(stored, ref, {ref: q[ref]} if ref in q else {})
    blocks_annual_head = _contributions(stored, ref, {ref: a[ref]} if ref in a else {})
    blocks = [blocks[0], blocks_annual_head[1]]
    prior, year = add_months(ref, -3), add_months(ref, -12)
    ev = lambda key, period: _evidence(row, stored, key, period)  # noqa: E731
    trend_ev = [ev(ALL, p) for p in (ref, prior, year) if p in levels]

    executive = [
        Insight(
            id="headline",
            kind="observation",
            text=_headline_text(q[ref], a[ref], ref, levels[ref]),
            evidence=trend_ev,
        )
    ]
    if prior in q and year in q:
        executive.append(
            Insight(
                id="quarter",
                kind="observation",
                text=f"Quarterly inflation of {q[ref]:.1f}% compares with {q[prior]:.1f}% in the "
                f"{_quarter(prior)} and {q[year]:.1f}% in the {_quarter(year)}.",
                evidence=[
                    ev(ALL, p)
                    for p in (ref, prior, add_months(prior, -3), year, add_months(year, -3))
                    if p in levels
                ],
            )
        )
    revisions, _ = _revisions(conn, row, stored)
    previous = repo.previous_vintage(conn, ALL, row["published_at"])
    old_points = repo.vintage_points(conn, previous.vintage_id) if previous else {}
    decompositions = []
    if old_points:
        old_annual = annual_changes({p: pt.value for p, pt in old_points.items()})
        prev_ref = max(old_points)
        if prev_ref in old_annual and prev_ref in a:
            decompositions.append(
                Decomposition(
                    label="CPI annual inflation, all groups (%)",
                    series_key=ALL,
                    previous_release_title=previous.title,
                    previous_period=prev_ref,
                    previous_published_value=old_annual[prev_ref],
                    same_period_now=a[prev_ref],
                    new_period=ref,
                    new_value=a[ref],
                    revision_component=a[prev_ref] - old_annual[prev_ref],
                    new_period_component=a[ref] - a[prev_ref],
                    total_change=a[ref] - old_annual[prev_ref],
                )
            )
    if decompositions:
        d = decompositions[0]
        executive.append(
            Insight(
                id="annual-vs-prior",
                kind="observation",
                text=f"Annual inflation of {a[ref]:.1f}% compares with {d.previous_published_value:.1f}% published for "
                f"the {_quarter(d.previous_period)} in the previous release, a change of "
                f"{d.total_change:+.1f} percentage points.",
                evidence=[ev(ALL, ref), ev(ALL, year), ev(ALL, d.previous_period)],
            )
        )
    else:
        executive.append(
            Insight(
                id="annual-vs-prior",
                kind="observation",
                text=f"Annual inflation was {a[ref]:.1f}%. No earlier publication of CPI is stored, so it cannot "
                "be compared with the previous release.",
                evidence=[ev(ALL, ref), ev(ALL, year)],
            )
        )
    tq, ta = quarterly_changes(trad), annual_changes(trad)
    nq, na = quarterly_changes(non), annual_changes(non)
    higher = (
        "Tradables" if ta[ref] > na[ref] else "Non-tradables" if na[ref] > ta[ref] else "Neither"
    )
    executive.append(
        Insight(
            id="tradability",
            kind="observation",
            text=f"Tradables inflation was {ta[ref]:.1f}% over the year ({tq[ref]:.1f}% in the quarter) and "
            f"non-tradables inflation was {na[ref]:.1f}% ({nq[ref]:.1f}%); "
            + (
                f"{higher.lower()} inflation was higher over the year. "
                if higher != "Neither"
                else "annual rates were equal. "
            )
            + "Contributions of tradables and non-tradables to the headline are not published in the files "
            "used, so this does not say which contributed more.",
            evidence=[ev("cpi.index.nsa.tradables", ref), ev("cpi.index.nsa.non_tradables", ref)],
        )
    )
    executive.append(_drivers(row, stored, ref, blocks))

    context = []
    window = [p for p in sorted(a) if p > add_months(ref, -120)]
    if len(window) > 4:
        hi, lo = max(window, key=a.get), min(window, key=a.get)
        context.append(
            Insight(
                id="history",
                kind="observation",
                text=f"Over the {len(window)} quarters to {month_label(ref)}, annual CPI inflation ranged from "
                f"{a[lo]:.1f}% ({_quarter(lo)}) to {a[hi]:.1f}% ({_quarter(hi)}); the latest rate is {a[ref]:.1f}%.",
                evidence=[ev(ALL, p) for p in (lo, hi, ref)],
            )
        )
    if old_points:
        changed = [p for p in set(old_points) & set(levels) if old_points[p].value != levels[p]]
        context.append(
            Insight(
                id="unadjusted-revisions",
                kind="observation",
                text="No previously published unadjusted all-groups index value changed in this release."
                if not changed
                else f"{len(changed)} previously published unadjusted all-groups index values changed in this release.",
                evidence=[ev(ALL, ref)],
            )
        )
    underlying = {k: v for k, v in stored.items() if k.startswith("cpi.underlying.")}
    tm, med = underlying.get("cpi.underlying.tm30"), underlying.get("cpi.underlying.median")
    if tm and med and tm[1] and med[1] and tm[1][-1].period == ref == med[1][-1].period:
        context.append(
            Insight(
                id="underlying",
                kind="observation",
                text=f"Stats NZ's published trimmed mean (30 percent trim) was {tm[1][-1].value:.1f}% and its "
                f"weighted median {med[1][-1].value:.1f}% for the quarter, against {q[ref]:.1f}% for all groups. "
                "These are official Stats NZ measures published with the release workbook.",
                evidence=[
                    Evidence(
                        series_key=k,
                        period=ref,
                        value=v[1][-1].value,
                        release_key=row["release_key"],
                    )
                    for k, v in (("cpi.underlying.tm30", tm), ("cpi.underlying.median", med))
                ],
            )
        )
    summary = release_summary(conn, row, analysable_slugs={SLUG})
    analysis = ReleaseAnalysis(
        release=summary,
        executive_summary=executive,
        headline_metrics=metrics,
        context=context,
        previous_comparison=PreviousComparison(
            available=bool(decompositions),
            note=revisions.note,
            previous_release_title=revisions.against_title,
            decompositions=decompositions,
        ),
        revisions=revisions,
        corrections=_corrections(conn, row["id"], bundle, vintage, primary_key=ALL),
        interpretation=[],
        methodology=Methodology(
            definitions=CAVEATS[:3], notes=CAVEATS[3:], source_url=row["page_url"]
        ),
        vintage_captured_at=to_akl_iso(vintage.captured_at),
    )
    series = _series_out(stored) if full else []
    return CpiDashboardOut(
        analysis=analysis,
        reference_period=ref,
        published_at=to_akl_iso(row["published_at"]),
        captured_at=to_akl_iso(vintage.captured_at),
        base=BASE_TEXT,
        series=series,
        contributions=blocks if full else [],
        underlying=[
            CpiUnderlyingOut(
                key=k,
                name=d.name,
                unit=d.unit,
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
            )
            for k, (d, obs) in sorted(underlying.items())
        ]
        if full
        else [],
        sources=sorted(
            {d.source_url for d, _ in stored.values() if d.source_url}
            | {row["page_url"] or ""} - {""}
        ),
        caveats=CAVEATS,
    )


def build_cpi_analysis(
    conn: sqlite3.Connection, release_id: int | None = None
) -> ReleaseAnalysis | None:
    result = _build(conn, release_id, full=False)
    return result.analysis if result else None


def build_cpi_dashboard(
    conn: sqlite3.Connection, release_id: int | None = None
) -> CpiDashboardOut | None:
    return _build(conn, release_id, full=True)

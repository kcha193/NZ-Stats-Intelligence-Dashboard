"""Deterministic analysis of an International migration release (no LLM, no causal claims)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Collection
from dataclasses import dataclass

from nzstats.adapters.migration.series import OUTCOMES_DEFINITION
from nzstats.clock import to_akl_iso
from nzstats.domain import ObsStatus, Point
from nzstats.insights.format import dir_word, fmt_int, fmt_net, fmt_signed
from nzstats.insights.summary import release_summary
from nzstats.models import (
    ChangeOut,
    Decomposition,
    Evidence,
    Insight,
    Methodology,
    Metric,
    PreviousComparison,
    ReleaseAnalysis,
    RevisionBlock,
    RevisionRowOut,
)
from nzstats.stats.changes import Change, lagged_change
from nzstats.stats.percentile import percentile_context
from nzstats.stats.periods import month_label
from nzstats.stats.revision import revisions, summarise
from nzstats.store import repo

SLUG = "international-migration"
NEEDED = (
    "mig.m.arrivals",
    "mig.m.departures",
    "mig.m.net",
    "mig.ry.arrivals",
    "mig.ry.departures",
    "mig.ry.net",
    "mig.ry.net.nz",
    "mig.ry.net.nonnz",
)
METRICS = (
    ("mig.ry.net", "Net migration, year ended"),
    ("mig.m.net", "Net migration, month"),
    ("mig.ry.arrivals", "Migrant arrivals, year ended"),
    ("mig.ry.departures", "Migrant departures, year ended"),
    ("mig.m.arrivals", "Migrant arrivals, month"),
    ("mig.m.departures", "Migrant departures, month"),
    ("mig.ry.net.nonnz", "Net migration, non-NZ citizens, year ended"),
    ("mig.ry.net.nz", "Net migration, NZ citizens, year ended"),
)
PERFECT = {"rose": "risen", "fell": "fallen"}
RANK_CAVEAT = (
    "Rank describes position within the published series only; it does not indicate "
    "economic significance."
)


@dataclass(frozen=True)
class _S:
    key: str
    unit: str
    frequency: str
    vintage: repo.VintageInfo
    obs: dict[str, repo.ObservationRow]

    @property
    def values(self) -> dict[str, float]:
        return {p: o.value for p, o in self.obs.items()}

    @property
    def latest(self) -> str:
        return max(self.obs)

    def label(self, period: str) -> str:
        if self.frequency == "rolling_annual":
            return f"year ended {month_label(period)}"
        return month_label(period)

    def evidence(self, period: str) -> Evidence:
        return Evidence(
            series_key=self.key,
            period=period,
            value=self.obs[period].value,
            release_key=self.vintage.release_key,
        )


def _load(
    conn: sqlite3.Connection, pick: Callable[[str], repo.VintageInfo | None]
) -> dict[str, _S] | None:
    out: dict[str, _S] = {}
    for key in NEEDED:
        vintage, series = pick(key), repo.get_series_row(conn, key)
        if vintage is None or series is None:
            return None
        out[key] = _S(
            key,
            series["unit"],
            series["frequency"],
            vintage,
            repo.vintage_observations(conn, vintage.vintage_id),
        )
    return out


def _change(s: _S, lag: int) -> tuple[Change | None, ChangeOut | None]:
    ch = lagged_change(s.values, s.latest, lag)
    if ch is None:
        return None, None
    return ch, ChangeOut(
        label=f"vs {s.label(ch.comparison_period)}",
        comparison_period=ch.comparison_period,
        previous=ch.previous,
        absolute=ch.absolute,
        percent=ch.percent,
    )


def _metric(s: _S, label: str) -> Metric:
    o = s.obs[s.latest]
    _, prior = _change(s, 1)
    _, yago = _change(s, 12)
    period_label = s.label(s.latest)
    return Metric(
        series_key=s.key,
        label=label,
        value=o.value,
        unit=s.unit,
        frequency=s.frequency,
        period=s.latest,
        period_label=period_label[0].upper() + period_label[1:],
        status=o.status.value,
        std_error=o.std_error if o.status is ObsStatus.PROVISIONAL else None,
        change_prior=prior,
        change_year_ago=yago,
    )


def _points(s: _S) -> dict[str, Point]:
    return {p: Point(p, o.value, o.status) for p, o in s.obs.items()}


def _streak(values: dict[str, float]) -> tuple[int, str]:
    """Consecutive changes in the same direction ending at the latest period."""
    periods = sorted(values)
    direction, count = "", 0
    for i in range(len(periods) - 1, 0, -1):
        delta = values[periods[i]] - values[periods[i - 1]]
        step = "rose" if delta > 0 else "fell" if delta < 0 else ""
        if not step or (direction and step != direction):
            break
        direction, count = step, count + 1
    return count, direction


def build_release_analysis(
    conn: sqlite3.Connection, release_id: int, *, analysable_slugs: Collection[str]
) -> ReleaseAnalysis | None:
    row = repo.get_release_by_id(conn, release_id)
    if row is None or row["series_slug"] != SLUG:
        return None
    cur = _load(conn, lambda k: repo.release_vintage(conn, k, release_id))
    if cur is None:
        return None
    prev = _load(conn, lambda k: repo.previous_vintage(conn, k, row["published_at"]))
    summary = release_summary(conn, row, analysable_slugs=analysable_slugs)

    ry_net, ry_arr, ry_dep = cur["mig.ry.net"], cur["mig.ry.arrivals"], cur["mig.ry.departures"]
    m_net, m_arr, m_dep = cur["mig.m.net"], cur["mig.m.arrivals"], cur["mig.m.departures"]
    nz, nonnz = cur["mig.ry.net.nz"], cur["mig.ry.net.nonnz"]
    ye = ry_net.latest

    # ---- executive summary (observations)
    summary_items: list[Insight] = []
    net_now = ry_net.obs[ye].value
    status = ry_net.obs[ye].status.value
    ch_net, _ = _change(ry_net, 12)
    text = f"Net migration for the {ry_net.label(ye)} was {fmt_net(net_now)} ({status})"
    ev = [ry_net.evidence(ye)]
    if ch_net:
        text += (
            f", compared with {fmt_net(ch_net.previous)} "
            f"in the {ry_net.label(ch_net.comparison_period)}"
        )
        ev.append(ry_net.evidence(ch_net.comparison_period))
    summary_items.append(Insight(id="headline", kind="observation", text=text + ".", evidence=ev))

    mp = m_net.latest
    summary_items.append(
        Insight(
            id="monthly",
            kind="observation",
            text=(
                f"In {month_label(mp)}, estimated migrant arrivals were "
                f"{fmt_int(m_arr.obs[mp].value)} and departures {fmt_int(m_dep.obs[mp].value)}, "
                f"giving {fmt_net(m_net.obs[mp].value)} ({m_net.obs[mp].status.value})."
            ),
            evidence=[m_arr.evidence(mp), m_dep.evidence(mp), m_net.evidence(mp)],
        )
    )

    ch_arr, _ = _change(ry_arr, 12)
    ch_dep, _ = _change(ry_dep, 12)
    if ch_net and ch_arr and ch_dep:
        yp = ch_net.comparison_period
        summary_items.append(
            Insight(
                id="drivers",
                kind="observation",
                text=(
                    f"Compared with the {ry_net.label(yp)}, arrivals {dir_word(ch_arr.absolute)} "
                    f"by {fmt_int(abs(ch_arr.absolute))} and departures "
                    f"{dir_word(ch_dep.absolute)} by {fmt_int(abs(ch_dep.absolute))}; the change in "
                    f"net migration ({fmt_signed(ch_net.absolute)}) is the difference between "
                    f"the two."
                ),
                evidence=[
                    ry_arr.evidence(ye),
                    ry_arr.evidence(yp),
                    ry_dep.evidence(ye),
                    ry_dep.evidence(yp),
                    ry_net.evidence(ye),
                    ry_net.evidence(yp),
                ],
            )
        )

    # ---- previous release: revisions vs genuinely new reference periods
    rev_block, prev_cmp, rev_insight = _previous(cur, prev, m_net)
    summary_items.append(rev_insight)

    prov = sorted(p for p, o in m_net.obs.items() if o.status is ObsStatus.PROVISIONAL)
    if prov:
        se = m_net.obs[mp].std_error
        suffix = (
            f"; the latest monthly net estimate has a standard error of {fmt_int(se)}" if se else ""
        )
        summary_items.append(
            Insight(
                id="provisional",
                kind="observation",
                text=(
                    f"Estimates from {month_label(prov[0])} to {month_label(prov[-1])} are "
                    f"provisional and will be revised as travel outcomes become known{suffix}."
                ),
                evidence=[m_net.evidence(prov[0]), m_net.evidence(prov[-1])],
            )
        )
    else:
        summary_items.append(
            Insight(
                id="provisional",
                kind="observation",
                text="All estimates in this release are final.",
                evidence=[m_net.evidence(mp)],
            )
        )

    # ---- context
    context: list[Insight] = []
    ctx = percentile_context(net_now, list(ry_net.values.values()))
    if ctx:
        first = min(ry_net.obs)
        context.append(
            Insight(
                id="history",
                kind="observation",
                text=(
                    f"The {ry_net.label(ye)} net figure ranks #{ctx.rank} highest of {ctx.n} "
                    f"year-ended observations since {month_label(first)}."
                ),
                evidence=[ry_net.evidence(ye)],
                caveat=RANK_CAVEAT,
            )
        )
    context.append(
        Insight(
            id="citizenship",
            kind="observation",
            text=(
                f"By citizenship, net migration of non-NZ citizens was "
                f"{fmt_net(nonnz.obs[nonnz.latest].value)} and of NZ citizens "
                f"{fmt_net(nz.obs[nz.latest].value)} ({nonnz.label(nonnz.latest)})."
            ),
            evidence=[nonnz.evidence(nonnz.latest), nz.evidence(nz.latest)],
        )
    )

    # ---- interpretation (arithmetic observation + one hedged inference)
    interpretation: list[Insight] = []
    if ch_arr and ch_dep and (abs(ch_arr.absolute) + abs(ch_dep.absolute)) > 0:
        arr_part, dep_part = abs(ch_arr.absolute), abs(ch_dep.absolute)
        lead, share = ("Arrivals", arr_part) if arr_part >= dep_part else ("Departures", dep_part)
        interpretation.append(
            Insight(
                id="driver-share",
                kind="observation",
                text=(
                    f"{lead} account for {share / (arr_part + dep_part):.0%} of the combined "
                    f"movement in arrivals and departures behind the year-on-year change in net "
                    f"migration."
                ),
                evidence=[ry_arr.evidence(ye), ry_dep.evidence(ye)],
            )
        )
    streak, direction = _streak(ry_net.values)
    if streak >= 3:
        interpretation.append(
            Insight(
                id="streak",
                kind="inference",
                text=(
                    f"The year-ended net figure has {PERFECT[direction]} for {streak} consecutive "
                    f"months. Adjacent year-ended values share eleven of twelve months, so this "
                    f"persistence is partly mechanical and is not by itself evidence of a "
                    f"sustained shift or of its cause."
                ),
                evidence=[ry_net.evidence(ye)],
                caveat="Inference from the published series; the data do not identify causes.",
            )
        )

    methodology = Methodology(
        definitions=[
            OUTCOMES_DEFINITION,
            "Monthly figures are mean estimates; year-ended figures are Stats NZ's published "
            "rolling twelve-month totals. The two are different series and are never combined.",
        ],
        notes=[
            "Figures are the unrounded values in Stats NZ's published data files; the release "
            "headline text may state rounded figures.",
            "Final estimates are reported with a standard error of zero in the source files.",
        ],
        source_url=row["page_url"],
    )
    return ReleaseAnalysis(
        release=summary,
        executive_summary=summary_items,
        headline_metrics=[_metric(cur[k], label) for k, label in METRICS],
        context=context,
        previous_comparison=prev_cmp,
        revisions=rev_block,
        interpretation=interpretation,
        methodology=methodology,
        vintage_captured_at=to_akl_iso(m_net.vintage.captured_at),
    )


def _previous(
    cur: dict[str, _S], prev: dict[str, _S] | None, m_net: _S
) -> tuple[RevisionBlock, PreviousComparison, Insight]:
    if prev is None:
        note = (
            "No earlier vintage is stored for this series, so revisions and changes since the "
            "previous release cannot be assessed. Revision history only covers releases "
            "ingested by this monitor."
        )
        block = RevisionBlock(
            available=False,
            note=note,
            series_key="mig.m.net",
            against_title=None,
            n_common=0,
            n_revised=0,
            mean_abs=None,
            largest=[],
        )
        cmp_ = PreviousComparison(
            available=False, note=note, previous_release_title=None, decompositions=[]
        )
        return (
            block,
            cmp_,
            Insight(
                id="revisions",
                kind="observation",
                text=note,
                evidence=[m_net.evidence(m_net.latest)],
            ),
        )

    prev_net = prev["mig.m.net"]
    revs = revisions(_points(prev_net), _points(m_net))
    summ = summarise(revs)
    changed = sorted(
        (r for r in revs if r.absolute != 0), key=lambda r: abs(r.absolute), reverse=True
    )
    largest = [
        RevisionRowOut(
            period=r.period,
            original=r.original,
            revised=r.revised,
            absolute=r.absolute,
            percent=r.percent,
            original_status=r.original_status.value,
            revised_status=r.revised_status.value,
        )
        for r in changed[:8]
    ]
    title = prev_net.vintage.title
    block = RevisionBlock(
        available=True,
        note=f"Compared with the {title} release.",
        series_key="mig.m.net",
        against_title=title,
        n_common=summ.n_common,
        n_revised=summ.n_revised,
        mean_abs=summ.mean_abs,
        largest=largest,
    )
    if summ.max_abs is not None:
        top = summ.max_abs
        text = (
            f"Compared with the {title} release, {summ.n_revised} of {summ.n_common} overlapping "
            f"monthly net estimates were revised; the largest was {month_label(top.period)}: "
            f"{fmt_int(top.original)} to {fmt_int(top.revised)} ({fmt_signed(top.absolute)})."
        )
        evidence = [prev_net.evidence(top.period), m_net.evidence(top.period)]
    else:
        text = (
            f"Compared with the {title} release, none of the {summ.n_common} overlapping "
            f"monthly net estimates were revised."
        )
        evidence = [m_net.evidence(m_net.latest)]
    insight = Insight(id="revisions", kind="observation", text=text, evidence=evidence)

    decomposition = []
    for key, label in (
        ("mig.ry.net", "Net migration, year ended"),
        ("mig.m.net", "Net migration, month"),
    ):
        c, p = cur[key], prev[key]
        old_latest, new_latest = p.latest, c.latest
        if new_latest == old_latest or old_latest not in c.obs:
            continue
        a, b, n = p.obs[old_latest].value, c.obs[old_latest].value, c.obs[new_latest].value
        decomposition.append(
            Decomposition(
                label=label,
                series_key=key,
                previous_release_title=title,
                previous_period=old_latest,
                previous_published_value=a,
                same_period_now=b,
                new_period=new_latest,
                new_value=n,
                revision_component=b - a,
                new_period_component=n - b,
                total_change=n - a,
            )
        )
    cmp_ = PreviousComparison(
        available=True,
        note=(
            "Change since the previous release is split into the revision of the previous "
            "reference period and the movement to the new reference period."
        ),
        previous_release_title=title,
        decompositions=decomposition,
    )
    return block, cmp_, insight

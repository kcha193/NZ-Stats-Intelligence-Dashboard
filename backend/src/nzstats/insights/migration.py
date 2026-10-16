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
    CorrectionBlock,
    CorrectionRowOut,
    CorrectionSeriesOut,
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
from nzstats.stats.periods import add_months, month_label
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
)
# Year-ended citizenship series come from a chart Stats NZ omitted from some releases (e.g. September
# 2025); a release without them is analysed without the citizenship insight and metrics.
OPTIONAL = ("mig.ry.net.nz", "mig.ry.net.nonnz")
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
    for key in (*NEEDED, *OPTIONAL):
        vintage, series = pick(key), repo.get_series_row(conn, key)
        observations = (
            repo.vintage_observations(conn, vintage.vintage_id) if vintage is not None else {}
        )
        if vintage is None or series is None or not observations:
            # An optional series with nothing in this bundle is unavailable. A required one must
            # have data, or the analysis cannot be built.
            if key in OPTIONAL:
                continue
            return None
        out[key] = _S(key, series["unit"], series["frequency"], vintage, observations)
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
        if add_months(periods[i - 1], 1) != periods[i]:
            break  # a missing month: the two sides are not adjacent, so the run ends here
        delta = values[periods[i]] - values[periods[i - 1]]
        step = "rose" if delta > 0 else "fell" if delta < 0 else ""
        if not step or (direction and step != direction):
            break
        direction, count = step, count + 1
    return count, direction


def driver_share_text(d_arr: float, d_dep: float) -> str | None:
    """Who drove the year-on-year change in net migration, from the signed arrivals/departures changes.

    Net = arrivals - departures, so arrivals rising and departures rising (or both falling) pull net
    in opposite directions. Their shares of a "combined movement" would then credit the larger side
    for a net change that is only the difference between the two, so no share is stated. When the
    two do not move the same way, |change in net| = |change in arrivals| + |change in departures|
    and the shares are exact.
    """
    if d_arr * d_dep > 0 or d_arr == d_dep == 0:
        return None
    arr_part, dep_part = abs(d_arr), abs(d_dep)
    lead, share = ("Arrivals", arr_part) if arr_part >= dep_part else ("Departures", dep_part)
    return (
        f"{lead} account for {share / (arr_part + dep_part):.0%} of the year-on-year change in net "
        f"migration; arrivals and departures did not move in the same direction, so neither "
        f"offsets the other."
    )


def _runs(periods: list[str]) -> list[tuple[str, str]]:
    """Maximal runs of consecutive months, as (first, last), from any ordering."""
    runs: list[tuple[str, str]] = []
    for p in sorted(set(periods)):
        if runs and add_months(runs[-1][1], 1) == p:
            runs[-1] = (runs[-1][0], p)
        else:
            runs.append((p, p))
    return runs


def describe_provisional(periods: list[str]) -> tuple[str, list[str]]:
    """Sentence naming exactly the provisional months, and the periods that evidence it.

    A range is used only for months that are consecutive; provisional months with final (or missing)
    months between them are listed separately so the text never calls a final month provisional.
    """
    runs = _runs(periods)
    revised = "will be revised as travel outcomes become known"
    evidence = [p for run in runs for p in dict.fromkeys(run)]
    if len(runs) == 1:
        first, last = runs[0]
        if first == last:
            return f"The estimate for {month_label(first)} is provisional and {revised}", evidence
        return (
            f"Estimates from {month_label(first)} to {month_label(last)} are provisional and "
            f"{revised}",
            evidence,
        )
    parts = [month_label(a) if a == b else f"{month_label(a)} to {month_label(b)}" for a, b in runs]
    listing = f"{', '.join(parts[:-1])} and {parts[-1]}"
    return f"Provisional estimates are those for {listing}; they {revised}", evidence


def build_release_analysis(
    conn: sqlite3.Connection, release_id: int, *, analysable_slugs: Collection[str]
) -> ReleaseAnalysis | None:
    row = repo.get_release_by_id(conn, release_id)
    if row is None or row["series_slug"] != SLUG:
        return None
    # One bundle per release: after a corrected re-ingest every series comes from the corrected
    # bundle, and an optional series it no longer contains is unavailable, not borrowed from the old one.
    bundle = repo.release_bundle(conn, release_id)
    if bundle is None:
        return None
    cur = _load(conn, lambda k: repo.bundle_vintage(conn, k, release_id, bundle))
    if cur is None:
        return None
    prev = _load(conn, lambda k: repo.previous_vintage(conn, k, row["published_at"]))
    summary = release_summary(conn, row, analysable_slugs=analysable_slugs)

    ry_net, ry_arr, ry_dep = cur["mig.ry.net"], cur["mig.ry.arrivals"], cur["mig.ry.departures"]
    m_net, m_arr, m_dep = cur["mig.m.net"], cur["mig.m.arrivals"], cur["mig.m.departures"]
    nz, nonnz = cur.get("mig.ry.net.nz"), cur.get("mig.ry.net.nonnz")
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
        lead, evidence_periods = describe_provisional(prov)
        evidence = [m_net.evidence(p) for p in evidence_periods]
        text = f"{lead}{suffix}."
        if ry_net.obs[ye].status is ObsStatus.PROVISIONAL:
            # Year-ended figures quoted elsewhere in this release inherit the status of their months.
            text += " Year-ended totals that include a provisional month are provisional too."
            evidence.append(ry_net.evidence(ye))
        summary_items.append(
            Insight(id="provisional", kind="observation", text=text, evidence=evidence)
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
    # One period label covers both values only if both series end in the same period; a series whose
    # latest cell is blank would otherwise show an older figure under the newer period's name.
    if nz is not None and nonnz is not None and nz.latest == nonnz.latest:
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
    share_text = driver_share_text(ch_arr.absolute, ch_dep.absolute) if ch_arr and ch_dep else None
    if share_text:
        interpretation.append(
            Insight(
                id="driver-share",
                kind="observation",
                text=share_text,
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
        headline_metrics=[_metric(cur[k], label) for k, label in METRICS if k in cur],
        context=context,
        previous_comparison=prev_cmp,
        revisions=rev_block,
        corrections=_corrections(conn, release_id, bundle, m_net.vintage),
        interpretation=interpretation,
        methodology=methodology,
        vintage_captured_at=to_akl_iso(m_net.vintage.captured_at),
    )


def _corrections(
    conn: sqlite3.Connection, release_id: int, bundle: str, vintage: repo.VintageInfo
) -> CorrectionBlock:
    """Compare statistical data within this publication, independently of earlier releases."""
    captured_at = to_akl_iso(vintage.captured_at)
    bundles = repo.release_bundles(conn, release_id)
    current = None
    for previous_bundle in bundles:
        if previous_bundle == bundle:
            continue
        if current is None:
            current = {
                d.key: {o.period: o for o in observations}
                for d, observations in repo.bundle_series(conn, release_id, bundle)
            }
        previous = {
            d.key: {o.period: o for o in observations}
            for d, observations in repo.bundle_series(conn, release_id, previous_bundle)
        }
        changes = []
        for key in sorted(current.keys() | previous.keys()):
            old, new = previous.get(key, {}), current.get(key, {})
            periods = [p for p in sorted(old.keys() | new.keys()) if old.get(p) != new.get(p)]
            if not periods:
                continue
            rows = []
            for period in periods[:8]:
                a, b = old.get(period), new.get(period)
                rows.append(
                    CorrectionRowOut(
                        period=period,
                        original=a.value if a else None,
                        revised=b.value if b else None,
                        original_status=a.status.value if a else None,
                        revised_status=b.status.value if b else None,
                        original_std_error=a.std_error if a else None,
                        revised_std_error=b.std_error if b else None,
                        original_released_in=a.released_in if a else None,
                        revised_released_in=b.released_in if b else None,
                    )
                )
            definition = repo.get_series_row(conn, key)
            changes.append(
                CorrectionSeriesOut(
                    series_key=key,
                    label=definition["name"],
                    unit=definition["unit"],
                    n_changed=len(periods),
                    changes=rows,
                )
            )
        if not changes:
            # Legacy source digests may contain editorial-only captures. Keep them in history, but
            # do not label identical statistical observations as a correction.
            continue
        prior = repo.bundle_vintage(conn, "mig.m.net", release_id, previous_bundle)
        return CorrectionBlock(
            available=True,
            note=(
                "Changes within this publication, compared with its previous distinct statistical "
                "capture. These are separate from revisions since an earlier publication. "
                "Each series lists up to eight changed periods; counts include all changed periods."
            ),
            against_captured_at=to_akl_iso(prior.captured_at) if prior else None,
            captured_at=captured_at,
            series=changes,
        )
    return CorrectionBlock(
        available=False,
        note="No earlier distinct statistical capture is stored for this publication.",
        against_captured_at=None,
        captured_at=captured_at,
        series=[],
    )


def _previous(
    cur: dict[str, _S], prev: dict[str, _S] | None, m_net: _S
) -> tuple[RevisionBlock, PreviousComparison, Insight]:
    if prev is None:
        note = (
            "No earlier publication is stored for this series, so revisions and changes since the "
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

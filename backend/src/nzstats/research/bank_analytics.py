"""Deterministic bank analytics (Phase 4AE): comparison, consensus, divergence, revisions and evaluation.

The existing functions (`compare_forecasts`, `consensus`, `forecast_history`, `evaluate_forecasts`) are called
unchanged. This module decides only what they are given:

- Differently adjusted figures are never aggregated: each comparison group is split by adjustment first, because
  `compare.py` deliberately ignores seasonal-adjustment wording when grouping.
- Consensus, divergence, revisions and evaluation take only quarterly *outlook* reports with a publication date; a
  weekly note or an undated document is listed as excluded, never silently dropped. The forecast table
  (`bank_comparison`) takes every report kind.
- Different values from one bank on one date for the same measure and adjustment are a conflict, inside one document
  or across two: none is used, and the bank's older figures for that measure are not shown in their place.
- Reference institutions (central bank, government) are markers on a group, never contributors.
- Freshness (Phase 4AH): in the current views (comparison, consensus, divergence) a bank's figure is not shown when the
  bank has a newer dated outlook report that was not fully read (`BankView.documents`) and neither that report nor a
  later one restates the measure. A refused table cell has no identity, so nothing is guessed about which measure it
  was. Revisions and evaluation keep every accepted vintage: they are history, not the bank's current view.

No model, network or database write is involved; `bank_evaluation` only reads stored Stats NZ vintages.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from nzstats.research.accuracy import Actuals, evaluate_forecasts
from nzstats.research.api_models import (
    ConsensusOut,
    ContributorOut,
    ForecastComparisonOut,
    ForecastEvaluationOut,
    ForecastHistoryOut,
    ForecastOut,
)
from nzstats.research.bank_forecast import Adjustment, NormalizedForecast, states_adjustment
from nzstats.research.bank_models import (
    BankConsensusGroupOut,
    BankConsensusOut,
    BankExclusionOut,
    BankVintageOut,
    ConsensusTitle,
    DivergenceBankOut,
    DivergenceOut,
)
from nzstats.research.bank_view import BankView
from nzstats.research.compare import CONFLICT, compare_forecasts, group_key, resolve
from nzstats.research.consensus import consensus
from nzstats.research.history import forecast_history
from nzstats.research.macro_outcomes import gdp_actuals, unemployment_actuals
from nzstats.research.outcomes import CpiActuals, Outcome, Target

ADJUSTMENTS: tuple[Adjustment, ...] = ("seasonally_adjusted", "unadjusted", "not_stated")
REASONS = {
    "not_outlook_report": "Only quarterly outlook reports feed this analysis.",
    "no_publication_date": "The document has no publication date, so its vintage cannot be placed.",
    "conflicting_forecasts": (
        "This bank gave different values for the same measure on one date (in one document or"
        " in two), so none of them is used."
    ),
    "newer_claim_unusable": (
        "This bank's newer report has a claim for the same measure that could not be used,"
        " so its older figure is not shown in its place."
    ),
    "newer_report_incomplete": (
        "This bank's newer report has table cells that could not be read,"
        " so its older figure is not shown as current."
    ),
    "newer_report_not_read": (
        "This bank has a newer report whose figures have not been read,"
        " so its older figure is not shown as current."
    ),
}


@dataclass(frozen=True)
class _Prepared:
    partitions: dict[Adjustment, list[NormalizedForecast]]
    excluded: list[BankExclusionOut]


def _exclusion(n: NormalizedForecast, code: str) -> BankExclusionOut:
    return BankExclusionOut(
        institution_key=n.institution_key,
        summary_id=n.forecast.summary_id,
        claim_path=n.claim_path,
        code=code,
        reason=REASONS[code],
    )


def _resolve_by_adjustment(
    items: list[NormalizedForecast],
) -> tuple[list[tuple[tuple, NormalizedForecast]], list[tuple[tuple, NormalizedForecast]]]:
    """`compare.resolve` per adjustment: (comparable claims, claims in conflict inside one document), each with its key.

    `compare.group_key` ignores adjustment wording, so resolving everything together would call a seasonally adjusted
    and an unadjusted figure for one measure a conflict. Claims `resolve` leaves out for any other reason have no
    comparable key and are not returned.
    """
    by_adjustment: dict[Adjustment, list[NormalizedForecast]] = defaultdict(list)
    for n in items:
        by_adjustment[n.adjustment].append(n)
    comparable: list[tuple[tuple, NormalizedForecast]] = []
    conflicts: list[tuple[tuple, NormalizedForecast]] = []
    for adjustment in ADJUSTMENTS:
        group = by_adjustment.get(adjustment, [])
        by_object = {id(n.forecast): n for n in group}
        kept, excluded = resolve([n.forecast for n in group])
        comparable.extend((key, by_object[id(f)]) for key, f in kept)
        conflicts.extend(
            (group_key(e.forecast), by_object[id(e.forecast)])
            for e in excluded
            if e.reason == CONFLICT
        )
        # `resolve` keeps one copy of an identical repeat (prose and table) and reports neither the rest nor a reason.
        # They are the same claim: give each the identity of the copy that was kept.
        accounted = {id(f) for _, f in kept} | {id(e.forecast) for e in excluded}
        comparable.extend(
            (group_key(n.forecast), n) for n in group if id(n.forecast) not in accounted
        )
    return comparable, conflicts


def _not_current(
    view: BankView, eligible: list[NormalizedForecast], key_of: dict[int, tuple]
) -> dict[int, str]:
    """Figures a newer, not fully read report of the same bank stops being current: id of the forecast -> code.

    A report blocks a figure when it is dated after the figure and no eligible figure of the same identity (bank,
    adjustment, comparison group) is dated on or after the report. A report whose only refused cells are scenario cells
    blocks scenario figures only.
    """
    blocking: dict[str, list[tuple[str, str, bool]]] = defaultdict(list)
    for d in view.documents:
        if d.state != "read":
            code = "newer_report_not_read" if d.state == "not_read" else "newer_report_incomplete"
            blocking[d.institution_key].append(
                (d.published_on, code, d.state == "incomplete_scenario")
            )
    if not blocking:
        return {}
    restated: dict[tuple, str] = {}
    for n in eligible:
        if (key := key_of.get(id(n.forecast))) is not None:
            identity = (n.institution_key, n.adjustment, key)
            restated[identity] = max(restated.get(identity, ""), n.forecast.published_on or "")
    out: dict[int, str] = {}
    for n in eligible:
        key = key_of.get(id(n.forecast))
        if key is None:
            continue
        # An undated figure cannot be shown to be newer than any dated report, so a newer unread one blocks it.
        dated = n.forecast.published_on or ""
        latest = restated[(n.institution_key, n.adjustment, key)]
        hits = [
            (day, code)
            for day, code, scenario_only in blocking.get(n.institution_key, [])
            if day > dated and latest < day and not (scenario_only and key[4] is None)
        ]
        if hits:
            out[id(n.forecast)] = max(hits)[1]
    return out


def _prepare(view: BankView, *, outlook_only: bool, dated_only: bool, current: bool) -> _Prepared:
    excluded: list[BankExclusionOut] = []
    eligible: list[NormalizedForecast] = []
    for n in view.forecasts:
        if outlook_only and n.report_kind != "outlook":
            excluded.append(_exclusion(n, "not_outlook_report"))
        elif dated_only and not n.forecast.published_on:
            excluded.append(_exclusion(n, "no_publication_date"))
        else:
            eligible.append(n)

    # The newest date on which a bank's claim for a measure could not be used: a conflict, or a failed or warned claim.
    # Any older figure of that bank for that measure is then not shown in its place (no carry-forward).
    newest_unusable: dict[tuple, str] = {}

    def note_unusable(n: NormalizedForecast, key: tuple) -> None:
        slot = (n.institution_key, n.adjustment, key)
        newest_unusable[slot] = max(newest_unusable.get(slot, ""), n.forecast.published_on or "")

    # One identity for every claim: the bank, the adjustment and the comparison group. Claims of one identity must agree
    # within a document and on a publication date; where they do not, none of them is used, and each blocks the bank's
    # older figures as an unusable claim does. Every claim is checked against every other of its identity, repeats and
    # claims from a report that disagrees with itself included.
    comparable, in_document = _resolve_by_adjustment(eligible)
    key_of = {id(n.forecast): key for key, n in (*comparable, *in_document)}
    by_identity: dict[tuple, list[NormalizedForecast]] = defaultdict(list)
    for key, n in (*comparable, *in_document):
        by_identity[(n.institution_key, n.adjustment, key)].append(n)
    conflicted: set[int] = set()
    for (_, _, key), members in by_identity.items():
        must_agree: dict[tuple, list[NormalizedForecast]] = defaultdict(list)
        for m in members:
            must_agree[("document", m.document_version_id)].append(m)
            if m.forecast.published_on:
                must_agree[("day", m.forecast.published_on)].append(m)
        for claims in must_agree.values():
            if len({c.forecast.value for c in claims}) > 1:
                for c in claims:
                    conflicted.add(id(c.forecast))
                    note_unusable(c, key)
    pool = [
        e.normalized
        for e in view.excluded
        if e.code
        in (
            "claim_failed_checks",
            "claim_has_warning",
        )  # a third party's or a no-number claim is not the bank's view
        and e.normalized is not None
        and e.normalized.forecast.published_on
        and (not outlook_only or e.normalized.report_kind == "outlook")
    ]
    # A pool claim that conflicts with another in its own document was still the bank's newest word on that measure.
    pool_kept, pool_conflicts = _resolve_by_adjustment(pool)
    for key, n in (*pool_kept, *pool_conflicts):
        note_unusable(n, key)
    stale = _not_current(view, eligible, key_of) if current else {}
    partitions: dict[Adjustment, list[NormalizedForecast]] = defaultdict(list)
    for n in eligible:
        newest = newest_unusable.get((n.institution_key, n.adjustment, key_of.get(id(n.forecast))))
        if id(n.forecast) in conflicted:
            excluded.append(_exclusion(n, "conflicting_forecasts"))
        elif newest and n.forecast.published_on and n.forecast.published_on < newest:
            excluded.append(_exclusion(n, "newer_claim_unusable"))
        elif id(n.forecast) in stale:
            excluded.append(_exclusion(n, stale[id(n.forecast)]))
        else:
            partitions[n.adjustment].append(n)
    return _Prepared(dict(partitions), excluded)


def bank_exclusions(
    view: BankView, *, outlook_only: bool, dated_only: bool, current: bool = True
) -> list[BankExclusionOut]:
    """What an analysis with these settings leaves out, with fixed codes and reasons (never document text).

    `current` is False for the history views (revisions, evaluation), which keep every accepted vintage.
    """
    return _prepare(
        view, outlook_only=outlook_only, dated_only=dated_only, current=current
    ).excluded


def _ordered(prepared: _Prepared):
    for adjustment in ADJUSTMENTS:
        if members := prepared.partitions.get(adjustment):
            yield adjustment, [n.forecast for n in members]


def bank_comparison(view: BankView) -> list[tuple[Adjustment, ForecastComparisonOut]]:
    prepared = _prepare(view, outlook_only=False, dated_only=False, current=True)
    return [(adj, compare_forecasts(fs)) for adj, fs in _ordered(prepared)]


def bank_revisions(view: BankView) -> list[tuple[Adjustment, ForecastHistoryOut]]:
    prepared = _prepare(view, outlook_only=True, dated_only=True, current=False)
    return [(adj, forecast_history(fs)) for adj, fs in _ordered(prepared)]


def _title(n: int) -> ConsensusTitle:
    if n >= 3:
        return "Consensus of banks"
    return "Two-bank comparison" if n == 2 else "Insufficient banks"


def _group_key(key: tuple) -> str:
    indicator, unit, basis, horizon_key, scenario = key
    return "|".join((indicator, unit, basis, horizon_key, scenario or "central"))


def _markers(view: BankView) -> dict[tuple[Adjustment, str], list[ContributorOut]]:
    """The newest forecast of each reference institution, by adjustment and comparison group."""
    kept, _ = _resolve_by_adjustment(view.markers)
    newest: dict[tuple[Adjustment, str, str], ForecastOut] = {}
    for key, n in kept:
        f = n.forecast
        slot = (n.adjustment, _group_key(key), f.institution.key)
        if slot not in newest or (f.published_on or "", f.summary_id) > (
            newest[slot].published_on or "",
            newest[slot].summary_id,
        ):
            newest[slot] = f
    out: dict[tuple[Adjustment, str], list[ContributorOut]] = defaultdict(list)
    for (adjustment, group, _), f in sorted(newest.items()):
        assert f.value is not None
        out[(adjustment, group)].append(
            ContributorOut(
                key=f.institution.key,
                name=f.institution.name,
                value=f.value,
                published_on=f.published_on,
                summary_id=f.summary_id,
            )
        )
    return out


def bank_consensus(view: BankView) -> BankConsensusOut:
    prepared = _prepare(view, outlook_only=True, dated_only=True, current=True)
    markers = _markers(view)
    groups: list[BankConsensusGroupOut] = []
    for adjustment, forecasts in _ordered(prepared):
        result: ConsensusOut = consensus(forecasts)
        for g in result.groups:
            groups.append(
                BankConsensusGroupOut(
                    **g.model_dump(),
                    adjustment=adjustment,
                    title=_title(g.n),
                    markers=markers.get((adjustment, g.key), []),
                )
            )
    return BankConsensusOut(groups=groups, excluded=prepared.excluded)


def bank_divergence(c: BankConsensusOut) -> list[DivergenceOut]:
    """Where banks disagree most: only groups with three or more contributors, widest spread first."""
    out = []
    for g in c.groups:
        if g.n < 3 or g.status != "available" or g.median is None or g.range is None:
            continue
        out.append(
            DivergenceOut(
                group_key=g.key,
                indicator=g.indicator,
                indicator_name=g.indicator_name,
                basis_label=g.basis_label,
                adjustment=g.adjustment,
                horizon_label=g.horizon_label,
                unit_label=g.unit_label,
                spread=g.range,
                median=g.median,
                # Ranked: highest forecast first, so the reader sees who is above and who is below the median.
                banks=[
                    DivergenceBankOut(
                        key=b.key,
                        name=b.name,
                        value=b.value,
                        distance_from_median=round(b.value - g.median, 6),
                    )
                    for b in sorted(g.contributors, key=lambda b: (-b.value, b.key))
                ],
            )
        )
    return sorted(out, key=lambda d: (-d.spread, d.group_key))


DISAGREEING_ADJUSTMENT = (
    "The seasonal adjustment is stated both ways (the label and the evidence disagree, or the evidence gives both),"
    " so the basis is unclear and it is not matched to an official figure."
)
ONLY_SA_STORED = (
    "Only the seasonally adjusted series is ingested for this measure,"
    " so an unadjusted forecast is not matched."
)
# Official measures held only as the seasonally adjusted series; the CPI measures and annual average GDP (computed from
# actual values) have an unadjusted version.
_SA_ONLY_MEASURES = frozenset(
    {
        "gdp_quarterly_production",
        "gdp_quarterly_expenditure",
        "gdp_annual_change_sa",
        "unemployment_rate",
    }
)


class _AdjustmentAwareActuals:
    """Official actuals that choose a series using the adjustment the bank layer derived, not the label alone.

    The matchers (`outcomes.cpi_target`, `macro_outcomes.gdp_target`, `unemployment_target`) read only
    `ForecastOut.indicator_label`, but the bank layer also takes the adjustment from the evidence quote. The matcher is
    shown the label with the derived adjustment added (when the label is silent); the forecast that is reported and
    scored keeps its own label. A forecast whose label and evidence disagree, or that asks for an unadjusted version of
    a measure held only seasonally adjusted, is excluded with a reason rather than matched to a different series.
    """

    def __init__(
        self, inner: Actuals, adjustments: dict[int, Adjustment], contradictory: set[int]
    ) -> None:
        self._inner = inner
        self._adjustments = adjustments
        self._contradictory = contradictory  # forecasts whose adjustment is stated both ways
        self.indicator = inner.indicator

    def adjustment_of(self, f: ForecastOut) -> Adjustment:
        return self._adjustments.get(id(f), "not_stated")

    def target(self, f: ForecastOut) -> Target | str:
        adjustment = self.adjustment_of(f)
        if id(f) in self._contradictory:
            return DISAGREEING_ADJUSTMENT
        if adjustment == "not_stated":
            if states_adjustment(f.indicator_label):
                return DISAGREEING_ADJUSTMENT
            return self._inner.target(f)
        seen = f
        if not states_adjustment(f.indicator_label) and (
            adjustment == "seasonally_adjusted" or f.indicator == "cpi_inflation"
        ):
            words = "seasonally adjusted" if adjustment == "seasonally_adjusted" else "unadjusted"
            seen = f.model_copy(update={"indicator_label": f"{f.indicator_label} ({words})"})
        result = self._inner.target(seen)
        if (
            adjustment == "unadjusted"
            and isinstance(result, Target)
            and result.measure in _SA_ONLY_MEASURES
        ):
            return ONLY_SA_STORED
        return result

    def measure_label(self, measure: str) -> str:
        return self._inner.measure_label(measure)

    def release_date(self, quarter: str) -> str | None:
        return self._inner.release_date(quarter)

    def newest_release(self) -> tuple[str, str] | None:
        return self._inner.newest_release()

    def outcome(self, target: Target) -> Outcome | None:
        return self._inner.outcome(target)


def bank_evaluation(
    view: BankView, conn: sqlite3.Connection, indicator: str
) -> ForecastEvaluationOut:
    prepared = _prepare(view, outlook_only=True, dated_only=True, current=False)
    members = [n for adjustment in ADJUSTMENTS for n in prepared.partitions.get(adjustment, [])]
    forecasts = [n.forecast for n in members]
    inner = {"gdp": gdp_actuals, "unemployment": unemployment_actuals}.get(indicator, CpiActuals)(
        conn
    )
    actuals = _AdjustmentAwareActuals(
        inner,
        {id(n.forecast): n.adjustment for n in members},
        {id(n.forecast) for n in members if n.adjustment_conflict},
    )
    return evaluate_forecasts(
        forecasts, actuals, indicator=indicator, resolve_scope=actuals.adjustment_of
    )


# Worst first: when two reports share the newest date, the less completely read one decides.
_STATE_ORDER = ("not_read", "incomplete", "incomplete_scenario", "read")


def bank_vintages(view: BankView) -> list[BankVintageOut]:
    """Per bank with a dated outlook report: the newest published against the newest accepted (Phase 4AH)."""
    # Accepted: survives the analysis's own rules (conflicts, unusable newer claims), before freshness is applied.
    prepared = _prepare(view, outlook_only=True, dated_only=True, current=False)
    usable = [n for members in prepared.partitions.values() for n in members]
    out = []
    for key in sorted({d.institution_key for d in view.documents}):
        mine = [d for d in view.documents if d.institution_key == key]
        newest = max(d.published_on for d in mine)
        state = min((d.state for d in mine if d.published_on == newest), key=_STATE_ORDER.index)
        accepted = max(
            (n.forecast.published_on for n in usable if n.institution_key == key), default=None
        )
        out.append(
            BankVintageOut(
                institution_key=key,
                latest_published_on=newest,
                latest_accepted_on=accepted,
                state=state,
                current=state == "read" and accepted == newest,
            )
        )
    return out

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


def _prepare(view: BankView, *, outlook_only: bool, dated_only: bool) -> _Prepared:
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

    # Conflicts inside one document (two values for one measure) and across documents (same bank, measure, target and
    # date, different documents and values). Both block the bank's older figures, as an unusable claim does.
    kept, in_document = _resolve_by_adjustment(eligible)
    key_of = {id(n.forecast): key for key, n in kept}
    conflicted: set[int] = set()
    for key, n in in_document:
        conflicted.add(id(n.forecast))
        note_unusable(n, key)
    same_day: dict[tuple, list[NormalizedForecast]] = defaultdict(list)
    for key, n in kept:
        if n.forecast.published_on:
            same_day[(n.institution_key, n.adjustment, key, n.forecast.published_on)].append(n)
    for members in same_day.values():
        if (
            len({m.forecast.summary_id for m in members}) > 1
            and len({m.raw_value for m in members}) > 1
        ):
            conflicted.update(id(m.forecast) for m in members)
            note_unusable(members[0], key_of[id(members[0].forecast)])
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
    partitions: dict[Adjustment, list[NormalizedForecast]] = defaultdict(list)
    for n in eligible:
        newest = newest_unusable.get((n.institution_key, n.adjustment, key_of.get(id(n.forecast))))
        if id(n.forecast) in conflicted:
            excluded.append(_exclusion(n, "conflicting_forecasts"))
        elif newest and n.forecast.published_on and n.forecast.published_on < newest:
            excluded.append(_exclusion(n, "newer_claim_unusable"))
        else:
            partitions[n.adjustment].append(n)
    return _Prepared(dict(partitions), excluded)


def bank_exclusions(
    view: BankView, *, outlook_only: bool, dated_only: bool
) -> list[BankExclusionOut]:
    """What an analysis with these settings leaves out, with fixed codes and reasons (never document text)."""
    return _prepare(view, outlook_only=outlook_only, dated_only=dated_only).excluded


def _ordered(prepared: _Prepared):
    for adjustment in ADJUSTMENTS:
        if members := prepared.partitions.get(adjustment):
            yield adjustment, [n.forecast for n in members]


def bank_comparison(view: BankView) -> list[tuple[Adjustment, ForecastComparisonOut]]:
    prepared = _prepare(view, outlook_only=False, dated_only=False)
    return [(adj, compare_forecasts(fs)) for adj, fs in _ordered(prepared)]


def bank_revisions(view: BankView) -> list[tuple[Adjustment, ForecastHistoryOut]]:
    prepared = _prepare(view, outlook_only=True, dated_only=True)
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
    prepared = _prepare(view, outlook_only=True, dated_only=True)
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
                adjustment=g.adjustment,
                horizon_label=g.horizon_label,
                unit_label=g.unit_label,
                spread=g.range,
                median=g.median,
                banks=[
                    DivergenceBankOut(
                        key=b.key,
                        name=b.name,
                        value=b.value,
                        distance_from_median=round(b.value - g.median, 6),
                    )
                    for b in g.contributors
                ],
            )
        )
    return sorted(out, key=lambda d: (-d.spread, d.group_key))


DISAGREEING_ADJUSTMENT = (
    "The label and the evidence disagree on seasonal adjustment, so the basis is unclear"
    " and it is not matched to an official figure."
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

    def __init__(self, inner: Actuals, adjustments: dict[int, Adjustment]) -> None:
        self._inner = inner
        self._adjustments = adjustments
        self.indicator = inner.indicator

    def adjustment_of(self, f: ForecastOut) -> Adjustment:
        return self._adjustments.get(id(f), "not_stated")

    def target(self, f: ForecastOut) -> Target | str:
        adjustment = self.adjustment_of(f)
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
    prepared = _prepare(view, outlook_only=True, dated_only=True)
    members = [n for adjustment in ADJUSTMENTS for n in prepared.partitions.get(adjustment, [])]
    forecasts = [n.forecast for n in members]
    inner = {"gdp": gdp_actuals, "unemployment": unemployment_actuals}.get(indicator, CpiActuals)(
        conn
    )
    actuals = _AdjustmentAwareActuals(inner, {id(n.forecast): n.adjustment for n in members})
    return evaluate_forecasts(
        forecasts, actuals, indicator=indicator, resolve_scope=actuals.adjustment_of
    )

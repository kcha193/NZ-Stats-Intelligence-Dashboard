"""Deterministic bank analytics (Phase 4AE): comparison, consensus, divergence, revisions and evaluation.

The existing functions (`compare_forecasts`, `consensus`, `forecast_history`, `evaluate_forecasts`) are called
unchanged. This module decides only what they are given:

- Differently adjusted figures are never aggregated: each comparison group is split by adjustment first, because
  `compare.py` deliberately ignores seasonal-adjustment wording when grouping.
- Consensus, divergence, revisions and evaluation take only quarterly *outlook* reports with a publication date; a
  weekly note or an undated document is listed as excluded, never silently dropped. The forecast table
  (`bank_comparison`) takes every report kind.
- Two documents from one bank on one date with different values for the same measure are a conflict: neither is
  used (`compare.resolve` already does this inside one document).
- Reference institutions (central bank, government) are markers on a group, never contributors.

No model, network or database write is involved; `bank_evaluation` only reads stored Stats NZ vintages.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from nzstats.research.accuracy import evaluate_forecasts
from nzstats.research.api_models import (
    ConsensusOut,
    ContributorOut,
    ForecastComparisonOut,
    ForecastEvaluationOut,
    ForecastHistoryOut,
    ForecastOut,
)
from nzstats.research.bank_forecast import Adjustment, NormalizedForecast
from nzstats.research.bank_models import (
    BankConsensusGroupOut,
    BankConsensusOut,
    BankExclusionOut,
    ConsensusTitle,
    DivergenceBankOut,
    DivergenceOut,
)
from nzstats.research.bank_view import BankView
from nzstats.research.compare import compare_forecasts, resolve
from nzstats.research.consensus import consensus
from nzstats.research.history import forecast_history
from nzstats.research.macro_outcomes import gdp_actuals, unemployment_actuals
from nzstats.research.outcomes import CpiActuals

ADJUSTMENTS: tuple[Adjustment, ...] = ("seasonally_adjusted", "unadjusted", "not_stated")
REASONS = {
    "not_outlook_report": "Only quarterly outlook reports feed this analysis.",
    "no_publication_date": "The document has no publication date, so its vintage cannot be placed.",
    "conflicting_forecasts": (
        "Two documents from this bank on one date give different values for the same measure,"
        " so neither is used."
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


def _prepare(
    forecasts: list[NormalizedForecast], *, outlook_only: bool, dated_only: bool
) -> _Prepared:
    excluded: list[BankExclusionOut] = []
    eligible: list[NormalizedForecast] = []
    for n in forecasts:
        if outlook_only and n.report_kind != "outlook":
            excluded.append(_exclusion(n, "not_outlook_report"))
        elif dated_only and not n.forecast.published_on:
            excluded.append(_exclusion(n, "no_publication_date"))
        else:
            eligible.append(n)

    # Cross-document conflicts: same bank, same measure and target, same date, different documents and values.
    by_object = {id(n.forecast): n for n in eligible}
    kept, _ = resolve([n.forecast for n in eligible])
    same_day: dict[tuple, list[NormalizedForecast]] = defaultdict(list)
    for key, f in kept:
        if f.published_on:
            same_day[(f.institution.key, key, f.published_on)].append(by_object[id(f)])
    conflicted: set[int] = set()
    for members in same_day.values():
        if (
            len({m.forecast.summary_id for m in members}) > 1
            and len({m.raw_value for m in members}) > 1
        ):
            conflicted.update(id(m.forecast) for m in members)
    partitions: dict[Adjustment, list[NormalizedForecast]] = defaultdict(list)
    for n in eligible:
        if id(n.forecast) in conflicted:
            excluded.append(_exclusion(n, "conflicting_forecasts"))
        else:
            partitions[n.adjustment].append(n)
    return _Prepared(dict(partitions), excluded)


def _ordered(prepared: _Prepared):
    for adjustment in ADJUSTMENTS:
        if members := prepared.partitions.get(adjustment):
            yield adjustment, [n.forecast for n in members]


def bank_comparison(view: BankView) -> list[tuple[Adjustment, ForecastComparisonOut]]:
    prepared = _prepare(view.forecasts, outlook_only=False, dated_only=False)
    return [(adj, compare_forecasts(fs)) for adj, fs in _ordered(prepared)]


def bank_revisions(view: BankView) -> list[tuple[Adjustment, ForecastHistoryOut]]:
    prepared = _prepare(view.forecasts, outlook_only=True, dated_only=True)
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
    by_object = {id(n.forecast): n for n in view.markers}
    kept, _ = resolve([n.forecast for n in view.markers])
    newest: dict[tuple[Adjustment, str, str], ForecastOut] = {}
    for key, f in kept:
        slot = (by_object[id(f)].adjustment, _group_key(key), f.institution.key)
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
    prepared = _prepare(view.forecasts, outlook_only=True, dated_only=True)
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


def bank_evaluation(
    view: BankView, conn: sqlite3.Connection, indicator: str
) -> ForecastEvaluationOut:
    prepared = _prepare(view.forecasts, outlook_only=True, dated_only=True)
    forecasts = [f for _, fs in _ordered(prepared) for f in fs]
    actuals = {"gdp": gdp_actuals, "unemployment": unemployment_actuals}.get(indicator, CpiActuals)(
        conn
    )
    return evaluate_forecasts(forecasts, actuals, indicator=indicator)

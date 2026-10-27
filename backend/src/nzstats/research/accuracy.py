"""Forecast accuracy against official outcomes (Phase 3D-B). Deterministic and descriptive.

Every comparable central vintage of a CPI forecast is matched to the official outcome for the quarter and measure it
states (`outcomes`). Scenarios are not scored, nor is anything published on or after that outcome's release
(look-ahead). The error is forecast minus actual: positive means the forecast was too high. It is computed against the
first-published actual and, separately, the latest. Summaries (mean error, MAE, RMSE) are given per institution,
measure and horizon band from four outcomes, counted as distinct official target quarters: when an institution has
several vintages for one quarter in one band, only its latest-published one (ties: highest summary id) is in the
sample, so repeated updates neither lift a quarter over the minimum nor weight it more than another. A ranking is given only on a matched sample: the (target quarter,
horizon) cells that every institution with matched forecasts covered, at least eight of them; otherwise the reason is
shown. No significance test is run. Forecast revisions are a separate analysis (`history`).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from nzstats.research.api_models import (
    AccuracySummaryOut,
    ActualOut,
    CoverageOut,
    EvaluatedForecastOut,
    ExcludedForecastOut,
    ForecastEvaluationOut,
    ForecastOut,
    RankingEntryOut,
    RankingOut,
)
from nzstats.research.compare import resolve
from nzstats.research.outcomes import (
    MEASURES,
    NSA,
    Actual,
    CpiActuals,
    Target,
    akl_date,
    cpi_target,
    look_ahead,
)

MIN_FOR_SUMMARY = 4
SCENARIO_REASON = (
    "A scenario is conditional on its own assumptions, so it is not scored against the outcome."
)
MIN_FOR_RANKING = 8
EVALUATED_INDICATORS = {"cpi_inflation": NSA}
BANDS = (("h0", None, 0), ("h1_2", 1, 2), ("h3_4", 3, 4), ("h5_8", 5, 8), ("h9", 9, None))
_MONTHS = ("March", "June", "September", "December")


@dataclass(frozen=True)
class ErrorStats:
    n: int
    sufficient: bool
    mean_error: float | None
    mae: float | None
    rmse: float | None


def _r(x: float) -> float:
    return round(x, 6)


def error_stats(errors: list[float], minimum: int = MIN_FOR_SUMMARY) -> ErrorStats:
    n = len(errors)
    if n < minimum:
        return ErrorStats(n, False, None, None, None)
    return ErrorStats(n, True, _r(sum(errors) / n), _r(sum(abs(e) for e in errors) / n),
                      _r(math.sqrt(sum(e * e for e in errors) / n)))  # fmt: skip


def _quarter_index(year: int, month: int) -> int:
    return year * 4 + (month - 1) // 3


def horizon_quarters(published_on: str, quarter: str) -> int:
    """Quarters from the quarter containing the publication date to the target quarter (0: the same quarter)."""
    d = date.fromisoformat(published_on)
    return _quarter_index(int(quarter[:4]), int(quarter[5:])) - _quarter_index(d.year, d.month)


def band_of(h: int) -> str:
    return next(
        key for key, low, high in BANDS if (low is None or h >= low) and (high is None or h <= high)
    )


@dataclass(frozen=True)
class Ranking:
    available: bool
    reason: str
    matched_cells: int
    entries: tuple[RankingEntry, ...] = ()


@dataclass(frozen=True)
class RankingEntry:
    institution: str
    n: int
    mae: float
    rmse: float
    mean_error: float


def rank(rows: Iterable[Mapping]) -> Ranking:
    """Rank on the cells every institution covered. `rows`: institution, cell (target, horizon), error; one per pair."""
    by_inst: dict[str, dict[tuple, float]] = defaultdict(dict)
    for r in rows:
        by_inst[r["institution"]][r["cell"]] = r["error"]
    if len(by_inst) < 2:
        return Ranking(
            False, "A ranking needs at least two institutions with evaluated forecasts.", 0
        )
    common = set.intersection(*(set(cells) for cells in by_inst.values()))
    if len(common) < MIN_FOR_RANKING:
        n = len(common)
        some = "No target was" if n == 0 else f"Only {n} target{' was' if n == 1 else 's were'}"
        return Ranking(False, f"{some} forecast by every institution at the same horizon; a ranking needs at least"
                              f" {MIN_FOR_RANKING}.", n)  # fmt: skip
    entries = []
    for inst, cells in by_inst.items():
        stats = error_stats([cells[c] for c in sorted(common)], minimum=1)
        entries.append(RankingEntry(inst, stats.n, stats.mae, stats.rmse, stats.mean_error))  # type: ignore[arg-type]
    entries.sort(key=lambda e: (e.mae, e.institution))
    reason = (f"Matched sample of {len(common)} targets at the same horizons, against first-published outcomes."
              " Descriptive only: no significance test.")  # fmt: skip
    return Ranking(True, reason, len(common), tuple(entries))


def _actual(a: Actual) -> ActualOut:
    return ActualOut(
        value=a.value,
        release=a.release,
        released_on=akl_date(a.released_at),
        first_release=a.first_release,
    )


def _target_label(t: Target) -> str:
    return f"{_MONTHS[int(t.quarter[5:]) // 3 - 1]} {t.quarter[:4]} quarter"


def evaluate_forecasts(
    forecasts: list[ForecastOut], actuals: CpiActuals, *, indicator: str
) -> ForecastEvaluationOut:
    chosen = [f for f in forecasts if f.indicator == indicator]
    newest = actuals.newest_release()
    base = dict(indicator=indicator, official_series=EVALUATED_INDICATORS.get(indicator),
                actuals_as_of=newest[0] if newest else None,
                actuals_released_on=akl_date(newest[1]) if newest else None,
                min_for_summary=MIN_FOR_SUMMARY, min_for_ranking=MIN_FOR_RANKING)  # fmt: skip
    empty = dict(
        vintages_from=None,
        vintages_to=None,
        evaluated=[],
        excluded=[],
        summaries=[],
        rankings=[],
        coverage=[],
    )
    if indicator not in EVALUATED_INDICATORS:
        return ForecastEvaluationOut(state="no_official_series", **base, **empty)
    if not chosen:
        return ForecastEvaluationOut(state="nothing_to_evaluate", **base, **empty)

    kept, excluded = resolve(chosen)
    evaluated: list[EvaluatedForecastOut] = []
    for _, f in kept:
        if f.scenario:
            excluded.append(ExcludedForecastOut(forecast=f, reason=SCENARIO_REASON))
            continue
        target = cpi_target(f)
        if isinstance(target, str):
            excluded.append(ExcludedForecastOut(forecast=f, reason=target))
            continue
        reason = look_ahead(f.published_on, target.quarter, actuals.release_date(target.quarter))
        if reason is not None:
            excluded.append(ExcludedForecastOut(forecast=f, reason=reason))
            continue
        h = horizon_quarters(f.published_on, target.quarter)  # type: ignore[arg-type]
        outcome = actuals.outcome(target)
        assert f.value is not None
        evaluated.append(EvaluatedForecastOut(
            forecast=f, measure=target.measure, measure_label=MEASURES[target.measure][0],
            target_quarter=target.quarter, target_label=_target_label(target), horizon_quarters=h, band=band_of(h),
            status="matched" if outcome else "pending",
            first=_actual(outcome.first) if outcome else None, latest=_actual(outcome.latest) if outcome else None,
            error_first=_r(f.value - outcome.first.value) if outcome else None,
            error_latest=_r(f.value - outcome.latest.value) if outcome else None,
            outcome_revision=outcome.revision if outcome else None,
        ))  # fmt: skip
    evaluated.sort(key=lambda e: (e.measure, e.target_quarter, e.forecast.institution.key, e.forecast.published_on or "",
                                  e.forecast.summary_id))  # fmt: skip
    excluded.sort(
        key=lambda e: (
            e.forecast.institution.key,
            e.forecast.published_on or "",
            e.forecast.horizon,
        )
    )
    matched = [e for e in evaluated if e.status == "matched"]
    institutions = {f.institution.key: f.institution for f in chosen}

    sample: dict[
        tuple[str, str, str, str], EvaluatedForecastOut
    ] = {}  # one vintage per outcome quarter
    for e in sorted(matched, key=lambda e: (e.forecast.published_on or "", e.forecast.summary_id)):
        sample[(e.forecast.institution.key, e.measure, e.band, e.target_quarter)] = (
            e  # the latest vintage wins
        )
    groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for (inst, measure, band, _), e in sorted(sample.items()):
        groups[(inst, measure, band)].append(e.error_first)  # type: ignore[arg-type]
    summaries = []
    for (inst, measure, band), errors in sorted(groups.items()):
        s = error_stats(errors)
        summaries.append(AccuracySummaryOut(
            institution=institutions[inst], measure=measure, measure_label=MEASURES[measure][0], band=band, n=s.n,
            sufficient=s.sufficient, mean_error=s.mean_error, mae=s.mae, rmse=s.rmse,
        ))  # fmt: skip

    rankings = []
    for measure in sorted({e.measure for e in matched}):
        cells: dict[tuple, EvaluatedForecastOut] = {}
        for e in sorted((e for e in matched if e.measure == measure),
                        key=lambda e: (e.forecast.published_on or "", e.forecast.summary_id)):  # fmt: skip
            cells[(e.forecast.institution.key, e.target_quarter, e.horizon_quarters)] = (
                e  # latest vintage per cell
            )
        result = rank(
            {"institution": k[0], "cell": k[1:], "error": e.error_first} for k, e in cells.items()
        )
        rankings.append(RankingOut(
            measure=measure, measure_label=MEASURES[measure][0], available=result.available, reason=result.reason,
            matched_cells=result.matched_cells,
            entries=[RankingEntryOut(institution=institutions[x.institution], n=x.n, mae=x.mae, rmse=x.rmse,
                                     mean_error=x.mean_error) for x in result.entries],
        ))  # fmt: skip

    coverage = [
        CoverageOut(
            institution=inst,
            matched=sum(e.forecast.institution.key == key for e in matched),
            pending=sum(
                e.forecast.institution.key == key and e.status == "pending" for e in evaluated
            ),
            excluded=sum(x.forecast.institution.key == key for x in excluded),
        )
        for key, inst in sorted(institutions.items())
    ]
    dates = sorted(e.forecast.published_on for e in evaluated if e.forecast.published_on)
    return ForecastEvaluationOut(
        state="available", **base, vintages_from=dates[0] if dates else None, vintages_to=dates[-1] if dates else None,
        evaluated=evaluated, excluded=excluded, summaries=summaries, rankings=rankings, coverage=coverage,
    )  # fmt: skip

"""Descriptive consensus (Phase 3D-B): what independent institutions' latest central forecasts say together.

Built on the Phase 3C comparison groups, so only forecasts on the same indicator, unit, basis and horizon meet. Central
forecasts only (scenarios never form a baseline), one per institution (its latest vintage), excluding a document that
is itself a consensus or survey of other forecasters (not independent) and vintages more than 180 days older than the
newest contribution. Two institutions give the mean, median and range; three add the sample standard deviation; five
allow outliers beyond the median by more than three scaled median absolute deviations. Nothing here is calibrated or
predictive, and every group says so.
"""

from __future__ import annotations

import re
import statistics
from datetime import date

from nzstats.research.api_models import (
    ConsensusGroupOut,
    ConsensusOut,
    ContributorOut,
    ExcludedForecastOut,
    ForecastOut,
)
from nzstats.research.compare import compare_forecasts

STALE_DAYS = 180
MIN_FOR_CONSENSUS = 2
MIN_FOR_SPREAD = 3
MIN_FOR_OUTLIERS = 5
MAD_SCALE = 1.4826  # makes the MAD comparable to a standard deviation for normal data
OUTLIER_MADS = 3.0
_AGGREGATE = re.compile(r"\bconsensus\b|\bsurvey of (?:economists|forecasters)\b", re.IGNORECASE)
AGGREGATE_REASON = (
    "The document is itself a consensus or survey of other forecasters, so it is not independent."
)
STALE_REASON = f"Published more than {STALE_DAYS} days before the newest contribution, so it is left out as stale."
NO_DATE_REASON = "The document has no publication date, so its age cannot be checked."


def _r(x: float) -> float:
    return round(x, 6)


def _contributor(f: ForecastOut) -> ContributorOut:
    assert f.value is not None
    return ContributorOut(key=f.institution.key, name=f.institution.name, value=f.value,
                          published_on=f.published_on, summary_id=f.summary_id)  # fmt: skip


def consensus(forecasts: list[ForecastOut]) -> ConsensusOut:
    out = []
    for g in compare_forecasts(forecasts).groups:
        if g.kind != "central":
            continue
        excluded: list[ExcludedForecastOut] = []
        candidates = []
        for row in g.rows:
            f = row.forecast
            if _AGGREGATE.search(f.document_title):
                excluded.append(ExcludedForecastOut(forecast=f, reason=AGGREGATE_REASON))
            elif not f.published_on:
                excluded.append(ExcludedForecastOut(forecast=f, reason=NO_DATE_REASON))
            else:
                candidates.append(f)
        newest = max((f.published_on for f in candidates), default=None)
        kept = []
        for f in candidates:
            age = (date.fromisoformat(newest) - date.fromisoformat(f.published_on)).days  # type: ignore[arg-type]
            if age > STALE_DAYS:
                excluded.append(ExcludedForecastOut(forecast=f, reason=STALE_REASON))
            else:
                kept.append(f)
        values = [f.value for f in kept]
        n = len(values)
        enough = n >= MIN_FOR_CONSENSUS
        median = statistics.median(values) if enough else None
        outliers: list[ContributorOut] = []
        if n >= MIN_FOR_OUTLIERS:
            mad = statistics.median(abs(v - median) for v in values)  # type: ignore[operator]
            if mad > 0:
                limit = OUTLIER_MADS * MAD_SCALE * mad
                outliers = [_contributor(f) for f in kept if abs(f.value - median) > limit]  # type: ignore[operator]
        out.append(ConsensusGroupOut(
            key=g.key, indicator=g.indicator, indicator_name=g.indicator_name, unit=g.unit, unit_label=g.unit_label,
            basis=g.basis, basis_label=g.basis_label, horizon_key=g.horizon_key, horizon_label=g.horizon_label,
            status="available" if enough else "insufficient", n=n,
            mean=_r(statistics.fmean(values)) if enough else None, median=_r(median) if enough else None,
            minimum=min(values) if enough else None, maximum=max(values) if enough else None,
            range=_r(max(values) - min(values)) if enough else None,
            std_dev=_r(statistics.stdev(values)) if n >= MIN_FOR_SPREAD else None,
            outliers_assessed=n >= MIN_FOR_OUTLIERS, outliers=outliers,
            contributors=[_contributor(f) for f in kept], excluded=excluded, as_of=newest,
        ))  # fmt: skip
    return ConsensusOut(groups=out)

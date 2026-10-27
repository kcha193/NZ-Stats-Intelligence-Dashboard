"""Forecast history (Phase 3D-B): vintages of one forecast across successive publications.

An identity is an institution plus a comparison group (indicator, unit, statistical basis, horizon, central or a named
scenario; `compare.group_key`). Each published document's claim for an identity is a vintage. Vintages are ordered by
publication date, then summary id; the newest is current and the rest are kept as superseded. A revision is a change of
value between consecutive vintages of one identity. When an institution's consecutive documents state the same
indicator, horizon and kind on disjoint bases, the measure changed: that is reported on its own and is never a revision.
Ambiguous claims and same-document conflicts are listed with their reason and not used (`compare.resolve`).
"""

from __future__ import annotations

from collections import defaultdict

from nzstats.research.api_models import (
    ForecastHistoryOut,
    ForecastOut,
    ForecastSeriesOut,
    ForecastVintageOut,
    MeasureChangeOut,
)
from nzstats.research.compare import (
    INDICATOR_NAMES,
    UNIT_LABELS,
    basis_label,
    horizon_of,
    indicator_rank,
    resolve,
)

MEASURE_CHANGE_NOTE = (
    "The institution stated a different measure for this horizon in its next publication. The values are different"
    " statistics, so the change is not a revision."
)


def _order(f: ForecastOut) -> tuple[str, int]:
    return f.published_on or "", f.summary_id


def _round(x: float) -> float:
    return round(x, 6)  # float noise only: inputs are stated to at most a few decimals


def _vintages(members: list[ForecastOut]) -> list[ForecastVintageOut]:
    ordered = sorted(members, key=_order)
    out = []
    for i, f in enumerate(ordered):
        assert f.value is not None  # comparable forecasts always have a value
        previous = ordered[i - 1].value if i else None
        out.append(ForecastVintageOut(
            summary_id=f.summary_id, published_on=f.published_on, document_title=f.document_title, value=f.value,
            indicator_label=f.indicator_label, horizon=f.horizon, qualification=f.qualification,
            evidence=f.evidence, superseded=i < len(ordered) - 1,
            revision=None if previous is None else _round(f.value - previous),
        ))  # fmt: skip
    return out


def _target(key: tuple) -> str:
    indicator, unit, basis, horizon_key, scenario = key
    return "|".join((indicator, unit, basis, horizon_key, scenario or "central"))


def forecast_history(forecasts: list[ForecastOut]) -> ForecastHistoryOut:
    kept, excluded = resolve(forecasts)
    identities: dict[tuple, list[ForecastOut]] = defaultdict(list)
    for key, f in kept:
        identities[(f.institution.key, *key)].append(f)

    series = []
    for (inst_key, indicator, unit, basis, horizon_key, scenario), members in identities.items():
        vintages = _vintages(members)
        first = sorted(members, key=_order)[0]
        target = _target((indicator, unit, basis, horizon_key, scenario))
        series.append(ForecastSeriesOut(
            key=f"{inst_key}|{target}", target_key=target, institution=first.institution, indicator=indicator,
            indicator_name=INDICATOR_NAMES.get(indicator, indicator), unit=unit, unit_label=UNIT_LABELS[unit],
            basis=basis, basis_label=basis_label(basis, first.indicator_label, indicator), horizon_key=horizon_key,
            horizon_label=horizon_of(first.horizon)[1],  # type: ignore[index]
            kind="scenario" if scenario else "central",
            scenario=" ".join(first.scenario.split()) if scenario and first.scenario else None,
            vintages=vintages, latest=vintages[-1],
            n_revisions=sum(v.revision not in (None, 0) for v in vintages),
            total_revision=_round(vintages[-1].value - vintages[0].value) if len(vintages) > 1 else None,
        ))  # fmt: skip
    series.sort(key=lambda s: (indicator_rank(s.indicator), s.basis, s.horizon_key, s.kind, s.scenario or "",
                               s.institution.key))  # fmt: skip
    excluded.sort(key=lambda e: (indicator_rank(e.forecast.indicator), e.forecast.institution.key,
                                 _order(e.forecast), e.forecast.horizon))  # fmt: skip
    return ForecastHistoryOut(
        series=series, measure_changes=_measure_changes(kept), excluded=excluded
    )


def _measure_changes(kept: list[tuple[tuple, ForecastOut]]) -> list[MeasureChangeOut]:
    """Consecutive documents of one institution, indicator, horizon and kind whose bases do not overlap at all."""
    documents: dict[tuple, dict[tuple[str, int], dict[str, ForecastOut]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for (indicator, _unit, basis, horizon_key, scenario), f in kept:
        documents[(f.institution.key, indicator, horizon_key, scenario)][_order(f)][basis] = f
    out = []
    for (_, indicator, horizon_key, scenario), by_doc in documents.items():
        ordered = sorted(by_doc)
        for before, after in zip(ordered, ordered[1:], strict=False):
            old, new = by_doc[before], by_doc[after]
            if set(old) & set(new):
                continue
            a, b = old[min(old)], new[min(new)]
            out.append(MeasureChangeOut(
                institution=b.institution, indicator=indicator, indicator_name=INDICATOR_NAMES.get(indicator, indicator),
                horizon_key=horizon_key, horizon_label=horizon_of(b.horizon)[1],  # type: ignore[index]
                kind="scenario" if scenario else "central",
                scenario=" ".join(b.scenario.split()) if scenario and b.scenario else None,
                from_basis=min(old), from_basis_label=basis_label(min(old), a.indicator_label, indicator),
                to_basis=min(new), to_basis_label=basis_label(min(new), b.indicator_label, indicator),
                from_summary_id=a.summary_id, from_published_on=a.published_on,
                to_summary_id=b.summary_id, to_published_on=b.published_on, note=MEASURE_CHANGE_NOTE,
            ))  # fmt: skip
    out.sort(
        key=lambda m: (
            indicator_rank(m.indicator),
            m.institution.key,
            m.horizon_key,
            m.to_published_on or "",
        )
    )
    return out

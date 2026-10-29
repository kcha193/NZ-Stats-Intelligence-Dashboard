"""Official outcomes for GDP and unemployment forecasts (Phase 4C), from stored Stats NZ vintages. Read-only.

The CPI rules in `outcomes` are unchanged. These rules match only a stated basis and a single quarter, to the series
Stats NZ itself headlines, and read the figure exactly as published (1 d.p.), never a recomputation:

- GDP: real (chain-volume) growth only. Quarterly growth → seasonally adjusted quarterly change, production measure
  unless the label says expenditure. Annual average growth → the production measure's annual average change (from
  actual values; a seasonally adjusted annual average is not an official measure). The annual change of a quarter →
  the seasonally adjusted series only when the label says seasonally adjusted (Stats NZ's annual change on actual
  values is not stored). Nominal GDP, levels and any other part of GDP are not matched.
- Unemployment: the HLFS total unemployment rate (seasonally adjusted, Stats NZ's headline) for a named quarter. An
  average over a period, an end-of-period rate, a month or a part of the labour force is not matched.

Unlike CPI, where Stats NZ headlines the unadjusted quarterly change and both versions are stored, GDP growth and the
unemployment rate are headlined seasonally adjusted and only that version is stored, so a label that does not say
otherwise is matched to it, and the measure label says so. First published: the release whose reference period is the
target quarter, as originally stored; otherwise the earliest stored release holding it, labelled as such.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Mapping

from nzstats.research.api_models import ForecastOut
from nzstats.research.compare import basis_of, horizon_of
from nzstats.research.outcomes import Actual, Outcome, Target
from nzstats.store.repo import list_vintages, vintage_points

GDP_SLUG, LABOUR_SLUG = "gross-domestic-product", "labour-market-statistics"
GDP_MEASURES = {
    "gdp_quarterly_production": (
        "GDP quarterly growth (real, production measure, seasonally adjusted)",
        "gdp.production.cv.sa.pct_qoq",
    ),
    "gdp_quarterly_expenditure": (
        "GDP quarterly growth (real, expenditure measure, seasonally adjusted)",
        "gdp.expenditure.cv.sa.pct_qoq",
    ),
    "gdp_annual_average": (
        "GDP annual average growth (real, production measure)",
        "gdp.production.cv.nsa.pct_annual_avg",
    ),
    "gdp_annual_change_sa": (
        "GDP annual change of the quarter (real, production measure, seasonally adjusted)",
        "gdp.production.cv.sa.pct_yoy",
    ),
}
UNEMPLOYMENT_MEASURES = {
    "unemployment_rate": (
        "Unemployment rate (HLFS, seasonally adjusted)",
        "hlfs.rate.unemployment.sa",
    ),
}
_SA = re.compile(r"\bseasonally[- ]adjusted\b|\bs\.?a\.?\b", re.IGNORECASE)
# basis_of() sorts qualifier words, regardless of their order in the label.
_PRODUCTION, _EXPENDITURE = (
    ("", "production", "measure-production"),
    ("expenditure", "expenditure-measure"),
)
UNCLEAR = "The statistical basis is not stated clearly enough to match an official figure."
SINGLE_QUARTER = "The horizon does not name a single quarter (a calendar or fiscal year, or a month), so it is not matched."


def _quarter(f: ForecastOut, *, allow_year_to: bool) -> str | None:
    key = (horizon_of(f.horizon) or ("",))[0]
    kind, _, period = key.partition(":")
    if kind not in (("quarter", "year_to") if allow_year_to else ("quarter",)):
        return None
    return period if period[5:] in ("03", "06", "09", "12") else None


def gdp_target(f: ForecastOut) -> Target | str:
    """The official GDP measure and quarter a forecast states, or why it cannot be matched."""
    if f.indicator != "gdp":
        return "Not a GDP forecast."
    basis = basis_of(f.indicator, f.indicator_label, f.horizon, f.unit)
    if f.unit != "percent" or basis is None:
        return UNCLEAR
    base, _, part = basis.partition(":")
    if base.startswith("nominal_"):
        return "Nominal GDP growth is not evaluated: only real (chain-volume) growth rates are matched."
    if part not in _PRODUCTION + _EXPENDITURE:
        return "No official series is ingested for this part of GDP, so it cannot be evaluated."
    production, stated_sa = part in _PRODUCTION, bool(_SA.search(f.indicator_label))
    if base == "real_quarterly_change":
        quarter = _quarter(f, allow_year_to=False)
        if quarter is None:
            return "Quarterly growth needs a single quarter. " + SINGLE_QUARTER
        return Target(
            "gdp_quarterly_production" if production else "gdp_quarterly_expenditure", quarter
        )
    if base == "real_annual_average_change":
        if not production:
            return "No official annual average series is ingested for the expenditure measure."
        if stated_sa:
            return "Annual average growth is calculated from actual (unadjusted) values; a seasonally adjusted one is not an official measure."
        quarter = _quarter(f, allow_year_to=True)
        return Target("gdp_annual_average", quarter) if quarter else SINGLE_QUARTER
    if base == "real_annual_change":
        quarter = _quarter(f, allow_year_to=False)
        if quarter is None:
            return "The annual change of a quarter needs a single quarter. " + SINGLE_QUARTER
        if not production:
            return "No official annual change series is ingested for the expenditure measure."
        if not stated_sa:
            return (
                "The label does not say seasonally adjusted: Stats NZ's annual change of a quarter on actual values is "
                "not ingested, only the seasonally adjusted series, so it is not matched."
            )
        return Target("gdp_annual_change_sa", quarter)
    return UNCLEAR


def unemployment_target(f: ForecastOut) -> Target | str:
    """The official unemployment measure and quarter a forecast states, or why it cannot be matched."""
    if f.indicator != "unemployment":
        return "Not an unemployment forecast."
    basis = basis_of(f.indicator, f.indicator_label, f.horizon, f.unit)
    if basis is None:
        return UNCLEAR
    base, _, part = basis.partition(":")
    if part:
        return "No official series is ingested for this part of the labour force (only the total rate), so it is not matched."
    if base == "rate_average":
        return "An average rate over a period is not matched: the HLFS publishes a rate for each quarter."
    if base == "rate_end":
        return "An end-of-period rate is not matched: the HLFS rate is an estimate for the whole quarter."
    key = (horizon_of(f.horizon) or ("",))[0]
    if key.startswith("month:"):
        return "The horizon names a month; the HLFS rate is a quarterly estimate, so it is not matched."
    quarter = _quarter(f, allow_year_to=False)
    if base != "rate" or quarter is None:
        return SINGLE_QUARTER
    return Target("unemployment_rate", quarter)


class OfficialActuals:
    """Stored releases of one Stats NZ category, read as published, loaded once per request.

    The first-published view reads each release's earliest stored vintage (a later correction never replaces it); the
    latest view reads each release's current vintage, in `list_vintages` order.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        indicator: str,
        slug: str,
        measures: Mapping[str, tuple[str, str]],
        target: Callable[[ForecastOut], Target | str],
        official_series: str,
    ) -> None:
        self.indicator, self.official_series = indicator, official_series
        self._measures, self._target = measures, target
        rows = conn.execute(
            "SELECT release_key, reference_period, title, published_at FROM release WHERE series_slug = ?",
            (slug,),
        ).fetchall()
        self._releases = {
            r["reference_period"]: r["published_at"] for r in rows if r["reference_period"]
        }
        reference = {r["release_key"]: r["reference_period"] for r in rows}
        self._first: dict[str, list] = {}
        self._latest: dict[str, list] = {}
        for _, series in measures.values():
            current, earliest = {}, {}
            for info in list_vintages(conn, series):
                current[info.release_key] = info
                if (
                    info.release_key not in earliest
                    or info.vintage_id < earliest[info.release_key].vintage_id
                ):
                    earliest[info.release_key] = info

            def load(info):
                points = {p: pt.value for p, pt in vintage_points(conn, info.vintage_id).items()}
                return info, reference.get(info.release_key), points

            self._latest[series] = [load(i) for i in current.values()]
            self._first[series] = [
                load(i)
                for i in sorted(earliest.values(), key=lambda v: (v.published_at, v.vintage_id))
            ]

    def target(self, f: ForecastOut) -> Target | str:
        return self._target(f)

    def measure_label(self, measure: str) -> str:
        return self._measures[measure][0]

    def release_date(self, quarter: str) -> str | None:
        return self._releases.get(quarter)

    def newest_release(self) -> tuple[str, str] | None:
        stored = self._latest[self.official_series]
        return (stored[-1][0].title, stored[-1][0].published_at) if stored else None

    def outcome(self, target: Target) -> Outcome | None:
        series = self._measures[target.measure][1]
        first = _actual(self._first[series], target.quarter)
        latest = _actual(list(reversed(self._latest[series])), target.quarter)
        return Outcome(first, latest) if first and latest else None


def _actual(vintages: list, quarter: str) -> Actual | None:
    for info, reference, points in vintages:
        if quarter in points:
            return Actual(points[quarter], info.title, info.published_at, reference == quarter)
    return None


def gdp_actuals(conn: sqlite3.Connection) -> OfficialActuals:
    return OfficialActuals(
        conn,
        indicator="gdp",
        slug=GDP_SLUG,
        measures=GDP_MEASURES,
        target=gdp_target,
        official_series="gdp.production.cv.sa.pct_qoq",
    )


def unemployment_actuals(conn: sqlite3.Connection) -> OfficialActuals:
    return OfficialActuals(
        conn,
        indicator="unemployment",
        slug=LABOUR_SLUG,
        measures=UNEMPLOYMENT_MEASURES,
        target=unemployment_target,
        official_series="hlfs.rate.unemployment.sa",
    )

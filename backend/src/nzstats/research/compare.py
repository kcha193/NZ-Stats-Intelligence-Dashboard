"""Which published forecasts can be compared, and why the others cannot (Phase 3C).

Two forecasts are compared only when they share the indicator, unit, statistical basis, horizon and kind (the central
forecast, or the same named scenario). Every rule is deterministic and deliberately conservative: wording that could
mean two different things (GDP "growth in the year to March" can be an annual average or a change through the year)
is not compared, and the reason is shown instead. Nothing is converted, rebased or inferred.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from nzstats.research.api_models import (
    ExcludedForecastOut,
    FacetOut,
    ForecastComparisonOut,
    ForecastGroupOut,
    ForecastOut,
    ForecastRowOut,
)
from nzstats.research.verify import UNITS

INDICATOR_ORDER = ("gdp", "cpi_inflation", "ocr", "unemployment")
INDICATOR_NAMES = {
    "gdp": "GDP", "cpi_inflation": "CPI inflation", "ocr": "Official cash rate",
    "unemployment": "Unemployment", "employment": "Employment", "wages": "Wages",
    "interest_rates": "Interest rates", "house_prices": "House prices", "exchange_rate": "Exchange rate",
    "fiscal_balance": "Fiscal balance", "government_debt": "Government debt", "migration": "Migration",
    "trade": "Trade", "other": "Other",
}  # fmt: skip
UNIT_LABELS = {
    "percent": "%", "percentage_points": "percentage points", "basis_points": "basis points",
    "percent_of_gdp": "% of GDP", "nzd": "NZ$", "nzd_million": "NZ$ million", "nzd_billion": "NZ$ billion",
    "index": "index", "persons": "people", "ratio": "ratio",
}  # fmt: skip
BASIS_LABELS = {
    "annual_change": "Annual change (through the year)",
    "annual_average_change": "Annual average change",
    "quarterly_change": "Quarterly change",
    "rate": "Rate",
    "level": "Level (timing within the period not stated)",
    "level_average": "Average over the period",
    "level_end": "End of period",
    "share_of_gdp": "Share of GDP",
}

_MONTH = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?"
    r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
                "October", "November", "December")  # fmt: skip
_YEAR = r"(\d{4})"
_YEAR_TO = re.compile(rf"^(?:year|12 months) (?:to|ended|ending) {_MONTH} {_YEAR}$")
_QUARTER_MONTH_FIRST = re.compile(rf"^{_MONTH} {_YEAR} quarter$")
_QUARTER_OF = re.compile(rf"^{_MONTH} quarter(?: of)? {_YEAR}$")
_Q_FIRST = re.compile(rf"^q([1-4]) ?{_YEAR}$")
_Q_LAST = re.compile(rf"^{_YEAR} ?q([1-4])$")
_CALENDAR = re.compile(rf"^(?:calendar(?: year)? )?{_YEAR}(?: calendar year)?$")
_MONTH_YEAR = re.compile(rf"^(?:(?:by|at|in) )?{_MONTH} {_YEAR}$")
_END_OF = re.compile(rf"^(?:(?:by|at) )?(?:the )?end(?:-| of ){_YEAR}$")
_SPLIT = re.compile(rf"^{_YEAR} ?/ ?(\d{{2}}|\d{{4}})$")

_QUARTERLY = re.compile(r"\bquarterly\b|\bq/q\b|\bqoq\b|quarter[- ]on[- ]quarter", re.IGNORECASE)
_ANNUAL_AVERAGE = re.compile(r"\bannual\s+average\b|\baapc\b", re.IGNORECASE)
_THROUGH_YEAR = re.compile(
    r"through\s+the\s+year|year[- ]on[- ]year|\by/y\b|\byoy\b"
    r"|\bannual\s+(?:%|percent(?:age)?|per\s+cent)\s+change",
    re.IGNORECASE,
)
_ANNUAL = re.compile(r"\bannual\b", re.IGNORECASE)
_AVERAGE = re.compile(r"\baverage\b", re.IGNORECASE)
_END = re.compile(r"\bend\b", re.IGNORECASE)
_EXTREME = re.compile(r"\b(?:peak|trough|high|low)\b", re.IGNORECASE)


def _month(token: str) -> int:
    return next(i for i, name in enumerate(_MONTH_NAMES, 1) if name.lower().startswith(token[:3]))


def _sane(year: str) -> bool:
    return 1990 <= int(year) <= 2100


def horizon_of(text: str | None) -> tuple[str, str] | None:
    """(key, label) for a horizon stated in a recognised form; None for relative or unusual wording."""
    t = re.sub(r"\s+", " ", (text or "").strip().lower().rstrip(".")).removeprefix("the ")
    if m := _YEAR_TO.match(t):
        month, year = _month(m[1]), m[2]
        return (
            (f"year_to:{year}-{month:02d}", f"Year to {_MONTH_NAMES[month - 1]} {year}")
            if _sane(year)
            else None
        )
    quarter = None
    if m := _QUARTER_MONTH_FIRST.match(t) or _QUARTER_OF.match(t):
        quarter = (_month(m[1]), m[2])
    elif m := _Q_FIRST.match(t):
        quarter = (int(m[1]) * 3, m[2])
    elif m := _Q_LAST.match(t):
        quarter = (int(m[2]) * 3, m[1])
    if quarter is not None:
        month, year = quarter
        if month % 3 or not _sane(year):
            return None
        return f"quarter:{year}-{month:02d}", f"{_MONTH_NAMES[month - 1]} {year} quarter"
    if m := _CALENDAR.match(t):
        return (f"calendar:{m[1]}", f"Calendar year {m[1]}") if _sane(m[1]) else None
    if m := _MONTH_YEAR.match(t):
        month, year = _month(m[1]), m[2]
        return (
            (f"month:{year}-{month:02d}", f"{_MONTH_NAMES[month - 1]} {year}")
            if _sane(year)
            else None
        )
    if m := _END_OF.match(t):
        return (f"month:{m[1]}-12", f"December {m[1]}") if _sane(m[1]) else None
    if m := _SPLIT.match(t):
        first, second = int(m[1]), int(m[2][-2:])
        if not _sane(m[1]) or (first + 1) % 100 != second:
            return None
        label = f"{first}/{second:02d}"
        return f"split:{label}", f"{label} (as stated)"
    return None


def unit_of(unit: str | None) -> str | None:
    return unit if unit in UNITS else None


def basis_of(indicator: str, label: str, horizon: str, unit: str | None) -> str | None:
    """The statistical basis the label states, or None when it does not say clearly enough to compare."""
    text = f"{label} {horizon}"
    key = (horizon_of(horizon) or ("",))[0]
    if indicator == "cpi_inflation":
        if _QUARTERLY.search(text):
            return "quarterly_change"
        if _ANNUAL_AVERAGE.search(text):
            return "annual_average_change"
        if _ANNUAL.search(text) or _THROUGH_YEAR.search(text) or key.startswith("year_to:"):
            return "annual_change"
        return None
    if indicator == "unemployment":
        return "rate" if unit == "percent" else None
    if indicator == "ocr":
        if unit != "percent" or _EXTREME.search(label):
            return None
        if _AVERAGE.search(label):
            return "level_average"
        return "level_end" if _END.search(label) else "level"
    if unit == "percent_of_gdp":
        return "share_of_gdp"
    if _QUARTERLY.search(text):
        return "quarterly_change"
    if _ANNUAL_AVERAGE.search(text):
        return "annual_average_change"
    if _THROUGH_YEAR.search(text):
        return "annual_change"
    return None


def _exclusion(f: ForecastOut) -> str | None:
    if f.value is None:
        return "States a direction only, with no number to compare."
    if unit_of(f.unit) is None:
        return "No unit is stated, so the number cannot be compared."
    if horizon_of(f.horizon) is None:
        return "The horizon is relative or not in a recognised form, so it cannot be lined up with others."
    if basis_of(f.indicator, f.indicator_label, f.horizon, f.unit) is None:
        if f.indicator == "gdp":
            return (
                "The statistical basis is not stated clearly enough to compare: GDP growth can be an annual"
                " average or a change through the year."
            )
        return "The statistical basis is not stated clearly enough to compare."
    return None


def indicator_rank(indicator: str) -> tuple[int, str]:
    order = (
        INDICATOR_ORDER.index(indicator) if indicator in INDICATOR_ORDER else len(INDICATOR_ORDER)
    )
    return order, indicator


def _vintage(f: ForecastOut) -> tuple[str, int]:
    return f.published_on or "", f.summary_id


def _note(basis: str, institutions: int) -> str:
    if institutions < 2:
        return "Only one institution has a published forecast on this basis."
    if basis == "level":
        return "Timing within the period is not stated: an average and an end-of-period level can differ."
    return f"{institutions} institutions, on the same basis and horizon."


def compare_forecasts(forecasts: list[ForecastOut]) -> ForecastComparisonOut:
    groups: dict[tuple, list[ForecastOut]] = defaultdict(list)
    excluded: list[ExcludedForecastOut] = []
    for f in forecasts:
        reason = _exclusion(f)
        if reason is not None:
            excluded.append(ExcludedForecastOut(forecast=f, reason=reason))
            continue
        horizon_key, _ = horizon_of(f.horizon)  # type: ignore[misc]
        basis = basis_of(f.indicator, f.indicator_label, f.horizon, f.unit)
        scenario = " ".join(f.scenario.split()).lower() if f.scenario else None
        groups[(f.indicator, f.unit, basis, horizon_key, scenario)].append(f)

    out: list[ForecastGroupOut] = []
    for (indicator, unit, basis, horizon_key, scenario), members in groups.items():
        by_institution: dict[str, list[ForecastOut]] = defaultdict(list)
        for f in members:
            by_institution[f.institution.key].append(f)
        rows = []
        for key in sorted(by_institution):
            ordered = sorted(by_institution[key], key=_vintage, reverse=True)
            rows.append(ForecastRowOut(forecast=ordered[0], earlier_vintages=ordered[1:]))
        first = sorted(members, key=lambda f: (_vintage(f), f.institution.key))[0]
        out.append(
            ForecastGroupOut(
                key="|".join((indicator, unit, basis, horizon_key, scenario or "central")),
                indicator=indicator, indicator_name=INDICATOR_NAMES.get(indicator, indicator),
                unit=unit, unit_label=UNIT_LABELS[unit], basis=basis, basis_label=BASIS_LABELS[basis],
                horizon_key=horizon_key, horizon_label=horizon_of(first.horizon)[1],  # type: ignore[index]
                kind="scenario" if scenario else "central",
                scenario=" ".join(first.scenario.split()) if scenario and first.scenario else None,
                rows=rows, comparable=len(rows) >= 2, note=_note(basis, len(rows)),
            )
        )  # fmt: skip
    out.sort(
        key=lambda g: (
            indicator_rank(g.indicator),
            g.basis,
            g.horizon_key,
            g.kind,
            g.scenario or "",
        )
    )
    excluded.sort(key=lambda e: (indicator_rank(e.forecast.indicator), e.forecast.institution.key,
                                 _vintage(e.forecast), e.forecast.horizon))  # fmt: skip

    indicator_counts = Counter(f.indicator for f in forecasts)
    institution_names = {f.institution.key: f.institution.name for f in forecasts}
    institution_counts = Counter(f.institution.key for f in forecasts)
    horizons = {g.horizon_key: g.horizon_label for g in out}
    horizon_counts = Counter(g.horizon_key for g in out for r in g.rows)
    return ForecastComparisonOut(
        groups=out,
        excluded=excluded,
        indicators=[FacetOut(value=k, label=INDICATOR_NAMES.get(k, k), count=indicator_counts[k])
                    for k in sorted(indicator_counts, key=indicator_rank)],
        institutions=[FacetOut(value=k, label=institution_names[k], count=institution_counts[k])
                      for k in sorted(institution_counts)],
        horizons=[FacetOut(value=k, label=horizons[k], count=horizon_counts[k]) for k in sorted(horizons)],
    )  # fmt: skip

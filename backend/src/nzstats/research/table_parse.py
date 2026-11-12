"""Values, periods, actual-or-forecast markers and units as printed in a forecast table (Phase 4AF).

Pure functions. Each either returns exactly what is printed or a fixed rejection code; nothing is repaired, converted
or inferred. The original text is always kept by the caller beside any parsed number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

_MONTHS = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)  # fmt: skip
_MONTH_NAMES = tuple(m.title() for m in _MONTHS)

# ---------------------------------------------------------------- values

_MISSING = frozenset({"", "-", "–", "—", "−", "n/a", "na", "..", "...", "…"})
_FOOTNOTE = "*†‡¹²³⁴⁵⁶⁷⁸⁹"
_MAX_MAGNITUDE = Decimal(1_000_000)
_NUMBER = re.compile(r"^([-+−–]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?$")


@dataclass(frozen=True)
class ParsedValue:
    kind: Literal["number", "missing", "reject"]
    value: Decimal | None
    raw: str
    footnote: str | None = None
    code: str | None = None


def parse_value(text: str) -> ParsedValue:
    """A printed cell as a number, a missing marker, or a rejection. A lone dash is missing, never zero."""
    raw = text
    t = text.strip()
    if t.lower() in _MISSING:
        return ParsedValue("missing", None, raw)
    if t.startswith("(") and t.endswith(")"):
        return ParsedValue("reject", None, raw, code="bracketed_value")
    footnote = None
    if t and t[-1] in _FOOTNOTE:
        footnote, t = t[-1], t[:-1].rstrip()
    t = t.removesuffix("%").rstrip()
    m = _NUMBER.match(t)
    if not m:
        return ParsedValue("reject", None, raw, code="unrecognised_suffix")
    sign, whole, frac = m.groups()
    value = Decimal(f"{whole.replace(',', '')}{frac or ''}")
    if (
        value >= _MAX_MAGNITUDE
    ):  # a rate, growth figure or unemployment rate is never this large: a misread cell
        return ParsedValue("reject", None, raw, code="value_out_of_range")
    if sign in ("-", "−", "–") and value != 0:
        value = -value
    return ParsedValue("number", value, raw, footnote)


# ---------------------------------------------------------------- periods

PeriodKind = Literal["month_end", "year_to", "quarter", "calendar"]
RenderKind = Literal["quarter", "year_to", "calendar", "month"]


@dataclass(frozen=True)
class Period:
    """A period as printed. `month_end` ("Dec-26") does not say whether it is a quarter or a year; the row does."""

    kind: PeriodKind
    year: int
    month: int | None

    def render(self, as_kind: RenderKind) -> str | None:
        """The wording `compare.horizon_of` reads, or None when this period cannot be that kind."""
        if as_kind == "calendar":
            return f"calendar year {self.year}" if self.kind == "calendar" else None
        if self.month is None or self.kind == "calendar":
            return None
        name = _MONTH_NAMES[self.month - 1]
        if as_kind == "year_to":
            return f"year to {name} {self.year}" if self.kind in ("month_end", "year_to") else None
        if as_kind == "quarter":
            ok = self.kind in ("month_end", "quarter") and self.month % 3 == 0
            return f"{name} {self.year} quarter" if ok else None
        return f"{name} {self.year}" if self.kind == "month_end" else None


_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_YEAR = r"(\d{4}|\d{2})"
_MARK = re.compile(r"(?<=[\d\s)])\(?([fFeEpP])\)?$")
_P_MONTH = re.compile(rf"^{_MON}[ \-]?{_YEAR}(?: (yr|y/e|ye|year))?$", re.IGNORECASE)
_P_YEAR_TO = re.compile(rf"^(?:year|12 months) (?:to|ended|ending) {_MON} {_YEAR}$", re.IGNORECASE)
_P_Q_FIRST = re.compile(rf"^q([1-4])[ \-]?{_YEAR}$", re.IGNORECASE)
_P_Q_LAST = re.compile(rf"^{_YEAR}[ \-]?q([1-4])$", re.IGNORECASE)
_P_CALENDAR = re.compile(r"^(\d{4})$")
_G_YEAR_TO = re.compile(rf"year (?:to|ended|ending|end(?:ing)?)\s+{_MON}", re.IGNORECASE)
_G_YEAR = re.compile(r"\b(\d{4})\b")


def _month(token: str) -> int:
    return next(i for i, m in enumerate(_MONTHS, 1) if m.startswith(token.lower()[:3]))


def _full_year(token: str) -> int:
    return int(token) if len(token) == 4 else 2000 + int(token)


def _strip_mark(text: str) -> str:
    return _MARK.sub("", text.strip()).strip()


def _read_header(text: str) -> Period | None:
    t = " ".join(_strip_mark(text).split())
    if m := _P_YEAR_TO.match(t):
        return Period("year_to", _full_year(m[2]), _month(m[1]))
    if m := _P_MONTH.match(t):
        return Period("year_to" if m[3] else "month_end", _full_year(m[2]), _month(m[1]))
    if m := _P_Q_FIRST.match(t):
        return Period("quarter", _full_year(m[2]), int(m[1]) * 3)
    if m := _P_Q_LAST.match(t):
        return Period("quarter", _full_year(m[1]), int(m[2]) * 3)
    if m := _P_CALENDAR.match(t):
        return Period("calendar", int(m[1]), None)
    return None


def period_of(headers: tuple[str, ...]) -> tuple[Period | None, str | None]:
    """The column's period from its own header (the last), checked against any group header above it."""
    period = _read_header(headers[-1])
    if period is None or not (1990 <= period.year <= 2100):
        return None, "unparsed_period"
    for group in headers[:-1]:
        if m := _G_YEAR_TO.search(group):
            if _month(m[1]) != period.month or period.kind not in ("month_end", "year_to"):
                return None, "contradictory_period"
            period = Period("year_to", period.year, period.month)
        years = {int(y) for y in _G_YEAR.findall(group)}
        if years and period.year not in years:
            return None, "contradictory_period"
    return period, None


# ---------------------------------------------------------------- actual or forecast

_ACTUAL = re.compile(r"^(?:actuals?|historical|outturn)\b", re.IGNORECASE)
_FORECAST = re.compile(r"^(?:forecasts?|projections?|projected)\b", re.IGNORECASE)
_FORECAST_MARK = re.compile(r"(?<=[\d\s)])\(?[fF]\)?$")


def column_kind(headers: tuple[str, ...]) -> Literal["actual", "forecast", "unknown"]:
    """Only an explicit marker counts: a group header or a trailing f. Estimates (e) and provisional (p) are unknown."""
    stated: set[str] = set()
    for group in headers[:-1]:
        if _ACTUAL.match(group.strip()):
            stated.add("actual")
        elif _FORECAST.match(group.strip()):
            stated.add("forecast")
    own = headers[-1].strip()
    if _ACTUAL.match(own):
        stated.add("actual")
    elif _FORECAST.match(own) or _FORECAST_MARK.search(own):
        stated.add("forecast")
    return next(iter(stated)) if len(stated) == 1 else "unknown"  # type: ignore[return-value]


# ---------------------------------------------------------------- units

_PP = re.compile(r"percentage[- ]points?|\bppts?\b|\bpp\b", re.IGNORECASE)
_BPS = re.compile(r"basis points?|\bbps\b|\bbp\b", re.IGNORECASE)
_PCT_GDP = re.compile(r"%\s*of\s*gdp|per ?cent of gdp", re.IGNORECASE)
_PCT = re.compile(r"%|per ?cent\b|\bpercent\b", re.IGNORECASE)


# Units this phase does not read. A caption saying "(%)" must not turn a count or an amount into a percentage.
_OTHER_UNITS = re.compile(
    r"'?000s?\b|\bthousands?\b|\bmillions?\b|\bbillions?\b|\$|\bnzd\b|\bindex\b|\bpersons?\b"
    r"|\bpeople\b|\bhours?\b",
    re.IGNORECASE,
)


def _units_in(text: str) -> set[str]:
    found: set[str] = set()
    if _PP.search(text):
        found.add("percentage_points")
    if _BPS.search(text):
        found.add("basis_points")
    rest = _PCT_GDP.sub(" ", text)
    if rest != text:
        found.add("percent_of_gdp")
    if _PCT.search(rest):
        found.add("percent")
    return found


def unit_of_text(*texts: str) -> tuple[str | None, str | None]:
    """(unit, None) when the texts name one unit; (None, None) when none does; (None, code) when they disagree."""
    found: set[str] = set()
    for text in texts:
        if _OTHER_UNITS.search(text):
            return None, "unsupported_unit"
        found |= _units_in(text)
    if len(found) > 1:
        return None, "contradictory_unit"
    return (next(iter(found)) if found else None), None

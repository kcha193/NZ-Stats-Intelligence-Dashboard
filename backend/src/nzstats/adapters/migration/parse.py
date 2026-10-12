from __future__ import annotations

import csv
import io
import logging
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime

import pandas as pd

from nzstats.adapters.base import ParsedSeries
from nzstats.adapters.migration import series as S
from nzstats.domain import ErrorClass, IngestError, Observation, ObsStatus, SeriesDef
from nzstats.sources.release_page import Chart
from nzstats.stats.periods import add_months

log = logging.getLogger(__name__)

REGIONS = frozenset(
    {"Asia", "Europe", "The Americas", "Africa and the Middle East", "Oceania and Antarctica"}
)
UNALLOCATED = frozenset({"Not Stated"})

AGE_SEX_COLUMNS = [
    "year_month",
    "month_of_release",
    "passenger_type",
    "direction",
    "sex",
    "age",
    "estimate",
    "standard_error",
    "status",
]
CITIZENSHIP_COLUMNS = [
    "year_month",
    "month_of_release",
    "passenger_type",
    "direction",
    "citizenship",
    "visa",
    "country_of_residence",
    "estimate",
    "standard_error",
    "status",
]
_DIRECTIONS = {"Arrivals": "arrivals", "Departures": "departures", "Net": "net"}
_STATUS = {"Final": ObsStatus.FINAL, "Provisional": ObsStatus.PROVISIONAL}


def _layout(message: str) -> IngestError:
    return IngestError(ErrorClass.LAYOUT_CHANGED, message)


def _status(value: str) -> ObsStatus:
    try:
        return _STATUS[value]
    except KeyError:
        raise _layout(f"unknown status value {value!r}") from None


def _read(data: bytes, columns: Sequence[str], name: str) -> pd.DataFrame:
    try:
        return pd.read_csv(
            io.BytesIO(data),
            usecols=list(columns),
            dtype={"year_month": str, "month_of_release": str},
        )
    except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        log.warning("%s: unreadable or missing expected columns: %r", name, exc)
        raise _layout(
            f"{name}: unreadable or missing expected columns ({type(exc).__name__})"
        ) from exc


def _observations(key: str, frame: pd.DataFrame) -> tuple[Observation, ...]:
    # Some Stats NZ files (e.g. June 2024) repeat an identical row two or three times; the repeated value
    # equals the official figure, so exact copies are collapsed. Rows that disagree stay an error below.
    deduped = frame.drop_duplicates()
    if len(deduped) < len(frame):
        log.warning("%s: collapsed %d exact duplicate source rows", key, len(frame) - len(deduped))
    frame = deduped.sort_values("year_month")
    if not frame["year_month"].is_unique:
        raise _layout(f"{key}: duplicate periods in source")
    return tuple(
        Observation(
            key,
            r.year_month,
            float(r.estimate),
            _status(r.status),
            float(r.standard_error),
            r.month_of_release,
        )
        for r in frame.itertuples(index=False)
    )


def parse_age_sex_csv(data: bytes) -> list[ParsedSeries]:
    df = _read(data, AGE_SEX_COLUMNS, "age/sex csv")
    df = df[
        (df["sex"] == "TOTAL")
        & (df["age"] == "TOTAL")
        & (df["passenger_type"] == "Long-term migrant")
    ]
    out = []
    for direction, label in _DIRECTIONS.items():
        sub = df[df["direction"] == direction]
        if sub.empty:
            continue
        definition = S.monthly_def(label)
        out.append(ParsedSeries(definition, _observations(definition.key, sub)))
    return out


def parse_citizenship_country_csv(data: bytes, *, country_window: int = 36) -> list[ParsedSeries]:
    df = _read(data, CITIZENSHIP_COLUMNS, "citizenship/country csv")
    base = df[
        (df["visa"] == "TOTAL")
        & (df["passenger_type"] == "Long-term migrant")
        & (df["direction"] == "Arrivals")
    ]
    if base.empty:
        raise _layout("citizenship csv has no arrivals rows with visa == TOTAL")
    out: list[ParsedSeries] = []
    for citizenship, label in (("NZ", "nz"), ("non-NZ", "nonnz")):
        sub = base[(base["citizenship"] == citizenship) & (base["country_of_residence"] == "TOTAL")]
        if not sub.empty:
            definition = S.citizenship_monthly_def(label)
            out.append(ParsedSeries(definition, _observations(definition.key, sub)))
    cutoff = add_months(str(base["year_month"].max()), -(country_window - 1))
    places = base[
        (base["citizenship"] == "TOTAL")
        & (base["country_of_residence"] != "TOTAL")
        & (base["year_month"] >= cutoff)
    ]
    seen: dict[str, str] = {}
    for name, group in places.groupby("country_of_residence", sort=True):
        kind = "region" if name in REGIONS else "unallocated" if name in UNALLOCATED else "country"
        definition = S.country_def(str(name), kind)
        if definition.key in seen:
            raise _layout(
                f"series key collision {definition.key}: {name!r} vs {seen[definition.key]!r}"
            )
        seen[definition.key] = str(name)
        out.append(ParsedSeries(definition, _observations(definition.key, group)))
    return out


def find_rolling_chart(charts: Sequence[Chart], labels: Mapping[str, SeriesDef]) -> Chart | None:
    """The year-ended chart whose rows include every label in `labels`.

    Editors retitle these charts from release to release (stray spaces, abbreviations, a footnote
    typed into the title field), so the title is not used: the "Year ended" header plus the series
    row labels identify a chart reliably.
    """
    for chart in charts:
        rows = list(csv.reader(io.StringIO(chart.csv.lstrip("\ufeff"))))
        if not rows or rows[0][0].strip() != "Year ended":
            continue
        if set(labels) <= {row[0].strip() for row in rows[1:] if row}:
            return chart
    return None


def _chart_period(header: str) -> str:
    try:
        return datetime.strptime(header.strip(), "%b-%Y").strftime("%Y-%m")
    except ValueError:
        raise _layout(f"unexpected chart column header {header!r}") from None


def parse_wide_chart(csv_text: str, mapping: Mapping[str, SeriesDef]) -> list[ParsedSeries]:
    rows = list(csv.reader(io.StringIO(csv_text.lstrip("﻿"))))
    if len(rows) < 2:
        raise _layout("chart csv has no data rows")
    periods = [_chart_period(h) for h in rows[0][1:]]
    found: dict[str, ParsedSeries] = {}
    for row in rows[1:]:
        if not row:
            continue
        definition = mapping.get(row[0].strip())
        if definition is None:
            continue
        observations = []
        for period, cell in zip(periods, row[1:], strict=False):
            cell = cell.strip()
            if cell in ("", "..", "…"):
                continue
            try:
                observations.append(
                    Observation(definition.key, period, float(cell), ObsStatus.UNKNOWN)
                )
            except ValueError:
                raise _layout(f"non-numeric chart value {cell!r} for {definition.key}") from None
        found[row[0].strip()] = ParsedSeries(definition, tuple(observations))
    missing = [label for label in mapping if label not in found]
    if missing:
        raise _layout(f"chart is missing expected series: {missing}")
    return [found[label] for label in mapping]


def with_rolling_status(ps: ParsedSeries, monthly_status: Mapping[str, ObsStatus]) -> ParsedSeries:
    """A year-ended value is provisional if any of its twelve months is provisional."""
    out = []
    for obs in ps.observations:
        statuses = [monthly_status.get(add_months(obs.period, -i)) for i in range(12)]
        if any(s is None for s in statuses):
            status = ObsStatus.UNKNOWN
        elif any(s is ObsStatus.PROVISIONAL for s in statuses):
            status = ObsStatus.PROVISIONAL
        else:
            status = ObsStatus.FINAL
        out.append(replace(obs, status=status))
    return replace(ps, observations=tuple(out))

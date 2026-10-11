"""Series definitions for International migration (outcomes-based long-term migrants)."""

from __future__ import annotations

from nzstats.domain import Adjustment, Frequency, SeriesDef
from nzstats.slug import slugify

DEFINITION_ID = "migration.outcomes_based_long_term"
OUTCOMES_DEFINITION = (
    "Long-term migrant movements under Stats NZ's outcomes-based measure (a traveller is counted "
    "as a migrant if they spend 12 of the following 16 months in, or out of, New Zealand). Mean "
    "estimates, in people. Estimates for the most recent months are provisional and are revised "
    "as travel outcomes become known."
)
_NAME = {"arrivals": "Migrant arrivals", "departures": "Migrant departures", "net": "Net migration"}
_CIT = {"nz": "NZ citizens", "nonnz": "non-NZ citizens"}


def monthly_def(direction: str) -> SeriesDef:
    return SeriesDef(
        key=f"mig.m.{direction}",
        name=f"{_NAME[direction]} (monthly estimate)",
        unit="people",
        frequency=Frequency.MONTHLY,
        adjustment=Adjustment.NONE,
        definition=OUTCOMES_DEFINITION,
        definition_id=DEFINITION_ID,
        category="migration",
    )


def rolling_def(direction: str, citizenship: str | None = None) -> SeriesDef:
    key = f"mig.ry.{direction}" + (f".{citizenship}" if citizenship else "")
    who = f", {_CIT[citizenship]}" if citizenship else ""
    return SeriesDef(
        key=key,
        name=f"{_NAME[direction]}{who} (year ended)",
        unit="people",
        frequency=Frequency.ROLLING_ANNUAL,
        adjustment=Adjustment.NONE,
        definition=OUTCOMES_DEFINITION + " Rolling twelve-month total, as published by Stats NZ.",
        definition_id=DEFINITION_ID,
        category="migration",
    )


def citizenship_monthly_def(citizenship: str) -> SeriesDef:
    return SeriesDef(
        key=f"mig.m.arrivals.{citizenship}",
        name=f"Migrant arrivals, {_CIT[citizenship]} (monthly estimate)",
        unit="people",
        frequency=Frequency.MONTHLY,
        adjustment=Adjustment.NONE,
        definition=OUTCOMES_DEFINITION,
        definition_id=DEFINITION_ID,
        category="migration",
    )


def country_def(name: str, kind: str) -> SeriesDef:
    prefix = "region" if kind == "region" else "country"
    category = {
        "country": "migration:country",
        "region": "migration:region",
        "unallocated": "migration:unallocated",
    }[kind]
    return SeriesDef(
        key=f"mig.m.arrivals.{prefix}.{slugify(name)}",
        name=f"Migrant arrivals from {name} (monthly estimate)",
        unit="people",
        frequency=Frequency.MONTHLY,
        adjustment=Adjustment.NONE,
        definition=OUTCOMES_DEFINITION + " Place is the country of last permanent residence.",
        definition_id=DEFINITION_ID,
        category=category,
    )


G1_LABELS = {
    "Migrant arrivals": rolling_def("arrivals"),
    "Migrant departures": rolling_def("departures"),
    "Net migration": rolling_def("net"),
}
G3_LABELS = {
    "Migrant arrivals (NZ citizens)": rolling_def("arrivals", "nz"),
    "Migrant arrivals (non-NZ citizens)": rolling_def("arrivals", "nonnz"),
    "Migrant departures (NZ citizens)": rolling_def("departures", "nz"),
    "Migrant departures (non-NZ citizens)": rolling_def("departures", "nonnz"),
    "Net migration (NZ citizens)": rolling_def("net", "nz"),
    "Net migration (non-NZ citizens)": rolling_def("net", "nonnz"),
}
ROLLING_DIRECTION_CHART = "Estimated migration by direction, rolling year"
ROLLING_CITIZENSHIP_CHART = "Estimated migration by citizenship, rolling year"

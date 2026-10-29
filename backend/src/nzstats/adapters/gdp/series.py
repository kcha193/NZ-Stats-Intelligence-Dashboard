"""Explicit supported Stats NZ quarterly GDP identities. Every other series in the file is ignored.

Metadata is pinned exactly as observed in the March and June 2026 quarter releases (docs/data-sources/gdp.md),
including the per-capita MAGNITUDE values, which are inconsistent in the official file (6 on some series whose values
are dollars per person). The adapter compares metadata; it never scales a value by MAGNITUDE.
"""

from __future__ import annotations

from dataclasses import dataclass

from nzstats.domain import Adjustment, Frequency, SeriesDef

SLUG = "gross-domestic-product"
CSV_FILE = "gdp_csv"
SUBJECT = "National Accounts - SNA 2008 - SNE"
PRICE_BASE = "2009/10 prices"

_PRODUCTION = "Gross Domestic Product - production measure"
_EXPENDITURE = "Gross Domestic Product - expenditure measure"
_PER_CAPITA = "Per Capita in New Zealand dollars"
_FROM_PREVIOUS = "Percentage change from previous period"
_FROM_YEAR_EARLIER = "Percentage change from same period previous year"


@dataclass(frozen=True)
class Expected:
    units: str
    magnitude: str
    group: str
    title_1: str
    title_2: str = ""


@dataclass(frozen=True)
class Pinned:
    reference: str
    definition: SeriesDef
    expected: Expected


def _def(key: str, name: str, unit: str, adjustment: Adjustment, definition: str) -> SeriesDef:
    return SeriesDef(
        key=key,
        name=name,
        unit=unit,
        frequency=Frequency.QUARTERLY,
        adjustment=adjustment,
        definition=definition,
        definition_id=key,
        category="gdp",
    )


SA, NSA = Adjustment.SEASONALLY_ADJUSTED, Adjustment.NONE
MILLION_REAL = f"NZD million ({PRICE_BASE})"
MILLION_NOMINAL = "NZD million (current prices)"
PER_PERSON = "NZD per person"

PINNED: tuple[Pinned, ...] = (
    Pinned(
        "SNEQ.SG01RSC00B01",
        _def(
            "gdp.production.cv.sa",
            "GDP, production measure, real, seasonally adjusted",
            MILLION_REAL,
            SA,
            f"Gross domestic product, production measure, chain volume ({PRICE_BASE}), seasonally adjusted, "
            "quarterly, NZ$ million. Stats NZ's headline GDP measure.",
        ),
        Expected(
            "Dollars", "6", "Series, GDP(P), Chain volume, Seasonally adjusted, Total", _PRODUCTION
        ),
    ),
    Pinned(
        "SNEQ.SG01RAC00B01",
        _def(
            "gdp.production.cv.nsa",
            "GDP, production measure, real, actual",
            MILLION_REAL,
            NSA,
            f"Gross domestic product, production measure, chain volume ({PRICE_BASE}), actual (not seasonally "
            "adjusted), quarterly, NZ$ million.",
        ),
        Expected("Dollars", "6", "Series, GDP(P), Chain volume, Actual, Total", _PRODUCTION),
    ),
    Pinned(
        "SNEQ.SG02RSC00B15",
        _def(
            "gdp.expenditure.cv.sa",
            "GDP, expenditure measure, real, seasonally adjusted",
            MILLION_REAL,
            SA,
            f"Gross domestic product, expenditure measure, chain volume ({PRICE_BASE}), seasonally adjusted, "
            "quarterly, NZ$ million.",
        ),
        Expected(
            "Dollars", "6", "Series, GDP(E), Chain volume, Seasonally adjusted, Total", _EXPENDITURE
        ),
    ),
    Pinned(
        "SNEQ.SG02RAC00B15",
        _def(
            "gdp.expenditure.cv.nsa",
            "GDP, expenditure measure, real, actual",
            MILLION_REAL,
            NSA,
            f"Gross domestic product, expenditure measure, chain volume ({PRICE_BASE}), actual (not seasonally "
            "adjusted), quarterly, NZ$ million.",
        ),
        Expected("Dollars", "6", "Series, GDP(E), Chain volume, Actual, Total", _EXPENDITURE),
    ),
    Pinned(
        "SNEQ.SG02NSC00B15",
        _def(
            "gdp.expenditure.cp.sa",
            "GDP, expenditure measure, nominal, seasonally adjusted",
            MILLION_NOMINAL,
            SA,
            "Gross domestic product, expenditure measure, current prices (nominal, not adjusted for price "
            "changes), seasonally adjusted, quarterly, NZ$ million.",
        ),
        Expected(
            "Dollars", "6", "Series, GDP(E), Nominal, Seasonally adjusted, Total", _EXPENDITURE
        ),
    ),
    Pinned(
        "SNEQ.SG02NAC00B15Z",
        _def(
            "gdp.expenditure.cp.nsa",
            "GDP, expenditure measure, nominal, actual",
            MILLION_NOMINAL,
            NSA,
            "Gross domestic product, expenditure measure, current prices (nominal), actual (not seasonally "
            "adjusted), quarterly, NZ$ million.",
        ),
        Expected(
            "Dollars",
            "6",
            "Series, GDP(E), Nominal, Actual, Total",
            _EXPENDITURE,
            "Total All Institutional Sectors",
        ),
    ),
    Pinned(
        "SNEQ.SG09RSC00B01NZ",
        _def(
            "gdp.per_capita.production.cv.sa",
            "GDP per capita, production measure, real, seasonally adjusted",
            PER_PERSON,
            SA,
            f"Gross domestic product per person, production measure, chain volume ({PRICE_BASE}), seasonally "
            "adjusted, quarterly, NZ$ per person. The quarter's GDP divided by Stats NZ's population estimate.",
        ),
        Expected(
            "Dollars",
            "0",
            "Series, Per capita measure, Chain volume, Seasonally adjusted, Total",
            _PRODUCTION,
            _PER_CAPITA,
        ),
    ),
    Pinned(
        "SNEQ.SG09NSC00B15NZ",
        _def(
            "gdp.per_capita.expenditure.cp.sa",
            "GDP per capita, expenditure measure, nominal, seasonally adjusted",
            PER_PERSON,
            SA,
            "Gross domestic product per person, expenditure measure, current prices, seasonally adjusted, "
            "quarterly, NZ$ per person. The file declares MAGNITUDE 6 for this series; its values are dollars.",
        ),
        Expected(
            "Dollars",
            "6",
            "Series, Per capita measure, Nominal, Seasonally adjusted, Total",
            _EXPENDITURE,
            _PER_CAPITA,
        ),
    ),
    Pinned(
        "SNEQ.SG01RSC01B01PC",
        _def(
            "gdp.production.cv.sa.pct_qoq",
            "Quarterly GDP growth (production, real, seasonally adjusted)",
            "percent",
            SA,
            "Percentage change in seasonally adjusted real production GDP from the previous quarter, as "
            "published by Stats NZ (1 d.p.).",
        ),
        Expected(
            "Percent",
            "0",
            "Series, GDP(P), Chain volume, Seasonally adjusted, Total, Percentage change",
            _PRODUCTION,
            _FROM_PREVIOUS,
        ),
    ),
    Pinned(
        "SNEQ.SG01RSC01B01AC",
        _def(
            "gdp.production.cv.sa.pct_yoy",
            "Annual change in quarterly GDP (production, real, seasonally adjusted)",
            "percent",
            SA,
            "Percentage change in seasonally adjusted real production GDP from the same quarter a year earlier, "
            "as published by Stats NZ (1 d.p.). Not annual average growth.",
        ),
        Expected(
            "Percent",
            "0",
            "Series, GDP(P), Chain volume, Seasonally adjusted, Total, Percentage change",
            _PRODUCTION,
            _FROM_YEAR_EARLIER,
        ),
    ),
    Pinned(
        "SNEQ.SG01RAC01B01AC",
        _def(
            "gdp.production.cv.nsa.pct_annual_avg",
            "Annual average GDP growth (production, real)",
            "percent",
            NSA,
            "Percentage change in real production GDP for the year ended in the quarter against the previous "
            "year ended in the same quarter (sum of four actual quarters), as published by Stats NZ (1 d.p.). "
            "The release page's 'Annual growth' chart.",
        ),
        Expected(
            "Percent",
            "0",
            "Series, GDP(P), Rolling annual, Chain volume, Actual, Total, Percentage change",
            _PRODUCTION,
            _FROM_YEAR_EARLIER,
        ),
    ),
    Pinned(
        "SNEQ.SG02RSC31B15PC",
        _def(
            "gdp.expenditure.cv.sa.pct_qoq",
            "Quarterly GDP growth (expenditure, real, seasonally adjusted)",
            "percent",
            SA,
            "Percentage change in seasonally adjusted real expenditure GDP from the previous quarter, as "
            "published by Stats NZ (1 d.p.).",
        ),
        Expected(
            "Percent",
            "0",
            "Series, GDP(E), Chain volume, Seasonally adjusted, Total, Percentage change",
            _EXPENDITURE,
            _FROM_PREVIOUS,
        ),
    ),
)

BY_REFERENCE = {p.reference: p for p in PINNED}
BY_KEY = {p.definition.key: p for p in PINNED}
KEYS = tuple(BY_KEY)
HEADLINE = "gdp.production.cv.sa"

# Published percentage → (level series, kind) used to reconcile it independently.
RECONCILE = {
    "gdp.production.cv.sa.pct_qoq": ("gdp.production.cv.sa", "qoq"),
    "gdp.production.cv.sa.pct_yoy": ("gdp.production.cv.sa", "yoy"),
    "gdp.production.cv.nsa.pct_annual_avg": ("gdp.production.cv.nsa", "annual_avg"),
    "gdp.expenditure.cv.sa.pct_qoq": ("gdp.expenditure.cv.sa", "qoq"),
}
# Release page chart title → the published series it must equal at every common quarter.
PAGE_CHARTS = {
    "Quarterly growth": "gdp.production.cv.sa.pct_qoq",
    "Annual growth": "gdp.production.cv.nsa.pct_annual_avg",
}

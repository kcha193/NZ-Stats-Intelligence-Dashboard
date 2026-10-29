"""Explicit supported labour market identities: HLFS headline series and the headline Labour Cost Index.

The Household Labour Force Survey (HLFS), the Labour Cost Index (LCI) and the Quarterly Employment Survey (QES) are
different surveys measuring different things; their series keep separate categories and are never combined. QES is
not stored. Metadata is pinned exactly as observed in the March and June 2026 quarter releases
(docs/data-sources/labour-market.md): every field that is not empty or "NA".
"""

from __future__ import annotations

from dataclasses import dataclass

from nzstats.domain import Adjustment, Frequency, SeriesDef

SLUG = "labour-market-statistics"
ZIP_FILE = "labour_zip"
HLFS, LCI = "hlfs", "lci"
CATEGORY = {HLFS: "labour:hlfs", LCI: "labour:lci"}
LCI_BASE = "June 2009 quarter (=1000)"

_HLFS_SUBJECT = "Household Labour Force Survey - HLF"
_HLFS_GROUP = "Labour Force Status by Sex: Seasonally Adjusted"
_STATUS = "Persons Employed, Unemployed, Not in Labour Force (for current quarter)"
_LCI_SUBJECT = "Labour Cost Index - LCI"


@dataclass(frozen=True)
class Pinned:
    reference: str
    survey: str  # HLFS or LCI: the zip member the series comes from
    definition: SeriesDef
    metadata: dict[
        str, str
    ]  # every non-empty, non-"NA" field other than reference, period, value and status


def _def(
    survey: str, key: str, name: str, unit: str, adjustment: Adjustment, definition: str
) -> SeriesDef:
    return SeriesDef(
        key=key,
        name=name,
        unit=unit,
        frequency=Frequency.QUARTERLY,
        adjustment=adjustment,
        definition=definition,
        definition_id=key,
        category=CATEGORY[survey],
    )


def _hlfs(ref: str, key: str, name: str, unit: str, status: str, definition: str) -> Pinned:
    units, magnitude = ("Percent", "0") if unit == "percent" else ("Number", "3")
    return Pinned(
        ref,
        HLFS,
        _def(HLFS, key, name, unit, Adjustment.SEASONALLY_ADJUSTED, definition),
        {
            "UNITS": units,
            "MAGNTUDE": magnitude,
            "Subject": _HLFS_SUBJECT,
            "Group": _HLFS_GROUP,
            _STATUS: status,
            "Sex": "Total Both Sexes",
        },
    )


_SURVEY = "Household Labour Force Survey, seasonally adjusted, quarterly, people aged 15 and over."
THOUSANDS = "thousand people"

PINNED: tuple[Pinned, ...] = (
    _hlfs(
        "HLFQ.S1F3S",
        "hlfs.rate.unemployment.sa",
        "Unemployment rate (HLFS, seasonally adjusted)",
        "percent",
        "Unemployment Rate",
        "Unemployed people as a percentage of the labour force (employed plus unemployed). "
        + _SURVEY,
    ),
    _hlfs(
        "HLFQ.S1H3S",
        "hlfs.rate.employment.sa",
        "Employment rate (HLFS, seasonally adjusted)",
        "percent",
        "Employment Rate",
        "Employed people as a percentage of the working-age population. " + _SURVEY,
    ),
    _hlfs(
        "HLFQ.S1E3S",
        "hlfs.rate.participation.sa",
        "Labour force participation rate (HLFS, seasonally adjusted)",
        "percent",
        "Labour Force Participation Rate",
        "The labour force (employed plus unemployed) as a percentage of the working-age population. "
        + _SURVEY,
    ),
    Pinned(
        "HLFQ.SXJ3UZS",
        HLFS,
        _def(
            HLFS,
            "hlfs.rate.underutilisation.sa",
            "Underutilisation rate (HLFS, seasonally adjusted)",
            "percent",
            Adjustment.SEASONALLY_ADJUSTED,
            "Underutilised people (unemployed, underemployed and the potential labour force) as a percentage of the "
            "extended labour force (labour force plus potential labour force). "
            + _SURVEY
            + " From March 2004.",
        ),
        {
            "UNITS": "Percent",
            "MAGNTUDE": "0",
            "Subject": _HLFS_SUBJECT,
            "Group": "Underutilisation by Sex: Seasonally Adjusted",
            "Seasonally Adjusted/Trend Series": "Seasonally Adjusted",
            "Sex": "Total Both Sexes",
            "Underutilisation": "Underutilisation rate",
        },
    ),
    _hlfs(
        "HLFQ.S1A3S",
        "hlfs.level.employed.sa",
        "Employed people (HLFS, seasonally adjusted)",
        THOUSANDS,
        "Persons Employed in Labour Force",
        "Number of employed people, in thousands. " + _SURVEY,
    ),
    _hlfs(
        "HLFQ.S1B3S",
        "hlfs.level.unemployed.sa",
        "Unemployed people (HLFS, seasonally adjusted)",
        THOUSANDS,
        "Persons Unemployed in Labour Force",
        "Number of unemployed people (without work, available and actively seeking work), in thousands. "
        + _SURVEY,
    ),
    _hlfs(
        "HLFQ.S1Z3S",
        "hlfs.level.labour_force.sa",
        "Labour force (HLFS, seasonally adjusted)",
        THOUSANDS,
        "Total Labour Force",
        "Employed plus unemployed people, in thousands. " + _SURVEY,
    ),
    _hlfs(
        "HLFQ.S1D3S",
        "hlfs.level.working_age_population.sa",
        "Working-age population (HLFS, seasonally adjusted)",
        THOUSANDS,
        "Working Age Population",
        "The usually resident, non-institutionalised civilian population aged 15 and over, in thousands. "
        + _SURVEY,
    ),
    Pinned(
        "LCIQ.SG53Z9",
        LCI,
        _def(
            LCI,
            "lci.all_wages.index",
            "Labour Cost Index, all salary and wage rates",
            "index",
            Adjustment.NONE,
            "Labour Cost Index, all salary and wage rates (including overtime), all sectors combined, all "
            f"industries; base {LCI_BASE}. Measures the change in the price of labour for the same work of the "
            "same quality; it is not average earnings (that is the Quarterly Employment Survey). Not seasonally "
            "adjusted.",
        ),
        {
            "UNITS": "Index",
            "MAGNTUDE": "0",
            "Subject": _LCI_SUBJECT,
            "Group": "All Sectors Combined and Industry Group (ANZSIC06)(Base: June 2009 qtr (=1000))",
            "Series_title_1": "All Salary and Wage Rates",
            "Series_title_2": "All Industries Combined",
        },
    ),
    Pinned(
        "LCIQ.SG53Z9PC",
        LCI,
        _def(
            LCI,
            "lci.all_wages.pct_qoq",
            "Labour Cost Index, quarterly change",
            "percent",
            Adjustment.NONE,
            "Percentage change in the Labour Cost Index (all salary and wage rates, all sectors) from the previous "
            "quarter, as published by Stats NZ (1 d.p.). Not seasonally adjusted.",
        ),
        {
            "UNITS": "Percent",
            "MAGNTUDE": "0",
            "Subject": _LCI_SUBJECT,
            "Group": "All Sectors Combined and Industry Group (ANZSIC06) Percentage Change",
            "Series_title_1": "All Salary and Wage Rates",
            "Series_title_2": "All Industries Combined",
            "Series_title_3": "Percentage change from previous period",
        },
    ),
    Pinned(
        "LCIQ.SG53Z9AC",
        LCI,
        _def(
            LCI,
            "lci.all_wages.pct_yoy",
            "Labour Cost Index, annual change",
            "percent",
            Adjustment.NONE,
            "Percentage change in the Labour Cost Index (all salary and wage rates, all sectors) from the same "
            "quarter a year earlier, as published by Stats NZ (1 d.p.).",
        ),
        {
            "UNITS": "Percent",
            "MAGNTUDE": "0",
            "Subject": _LCI_SUBJECT,
            "Group": "All Sectors Combined and Industry Group (ANZSIC06) Percentage Change",
            "Series_title_1": "All Salary and Wage Rates",
            "Series_title_2": "All Industries Combined",
            "Series_title_3": "Percentage change from same period previous year",
        },
    ),
)

BY_REFERENCE = {p.reference: p for p in PINNED}
BY_KEY = {p.definition.key: p for p in PINNED}
KEYS = tuple(BY_KEY)
UNEMPLOYMENT = "hlfs.rate.unemployment.sa"
HEADER_REQUIRED = {
    HLFS: {
        "STATUS",
        "Series_reference",
        "Period",
        "Data_value",
        "UNITS",
        "MAGNTUDE",
        "Subject",
        "Group",
    },
    LCI: {
        "Series_reference",
        "Period",
        "Data_value",
        "STATUS",
        "UNITS",
        "MAGNTUDE",
        "Subject",
        "Group",
    },
}

"""Explicit supported Stats NZ ECT identities; annual and proportion series are excluded."""

import re

from nzstats.domain import Adjustment, Frequency, SeriesDef

SLUG = "electronic-card-transactions"
INDUSTRIES = {
    "1": ("consumables", "Consumables"),
    "2": ("durables", "Durables"),
    "3": ("hospitality", "Hospitality"),
    "4": ("services", "Services"),
    "5": ("apparel", "Apparel"),
    "6": ("motor_vehicles", "Motor vehicles excl. fuel"),
    "7": ("fuel", "Fuel"),
    "8": ("non_retail", "Non-retail excl. services"),
}
TOTALS = {
    "1": ("retail", "RTS total industries"),
    "2": ("core", "RTS core industries"),
    "9": ("total", "Total"),
    "W": ("credit", "Credit"),
    "X": ("debit", "Debit"),
}
ADJUSTMENTS = {
    "A": ("actual", "Actual", Adjustment.NONE),
    "S": ("sa", "Seasonally adjusted", Adjustment.SEASONALLY_ADJUSTED),
    "T": ("trend", "Trend", Adjustment.TREND),
}
VALUE_GROUP = "Total values - Electronic card transactions A/S/T by division"
INDUSTRY_GROUP = "Values - Electronic card transactions A/S/T by industry group"
COUNT_GROUP = "Number of electronic card transactions A/S/T by division"
CHANGE_GROUP = "Totals - Electronic card transactions by division, percentage changes"


def identity(code: str, source_url: str | None = None) -> tuple[SeriesDef, dict[str, str]] | None:
    match = re.fullmatch(r"ECT([MQ])\.S(19|1G|29)([AST])([1-9WX])(PC)?", code)
    average = re.fullmatch(r"ECT([MQ])\.S4A1V", code)
    if not match and not average:
        return None
    freq = (match or average)[1]
    group, adj, index, change = (
        (match[2], match[3], match[4], match[5]) if match else ("mean", "A", "9", None)
    )
    table = INDUSTRIES if group == "1G" else TOTALS
    if (
        index not in table
        or (group == "29" and adj != "A")
        or (change and (group != "19" or adj != "S"))
    ):
        raise ValueError("unsupported ECT series identity")
    industry, title = table[index]
    adjustment, adj_title, enum = ADJUSTMENTS[adj]
    measure = (
        "change" if change else "count" if group == "29" else "average" if average else "value"
    )
    unit, source_unit, magnitude = {
        "value": ("NZD million", "Dollars", "6"),
        "count": ("transactions", "Number", "0"),
        "average": ("NZD", "Dollars", "0"),
        "change": ("percent", "Percent", "0"),
    }[measure]
    expected = {
        "UNITS": source_unit,
        "Magnitude": magnitude,
        "Series_title_1": adj_title,
        "Series_title_2": "Mean transaction value" if average else title,
        "Series_title_3": "Value ($)"
        if average
        else "Percentage change from previous period"
        if change
        else "",
        "Group": CHANGE_GROUP
        if change
        else COUNT_GROUP
        if group == "29"
        else INDUSTRY_GROUP
        if group == "1G"
        else "Electronic card transactions by mean and proportion"
        if average
        else VALUE_GROUP,
        "Subject": "Electronic Card Transactions (ANZSIC06) - ECT",
        "Series_title_4": "",
        "Series_title_5": "",
    }
    name = {"retail": "Retail", "core": "Core retail", "total": "Total ECT"}.get(industry, title)
    frequency = Frequency.MONTHLY if freq == "M" else Frequency.QUARTERLY
    definition = (
        f"Stats NZ {code}; ANZSIC06; {title}; {measure}; {adj_title}; "
        f"{frequency.value}; nominal (not price-adjusted). Official units {source_unit}, "
        f"magnitude {magnitude}. Independently adjusted components may not sum to totals. "
        "F=final, P=provisional; R=revised is normalised to unknown status and remains revisable."
    )
    return SeriesDef(
        f"ect.{freq.lower()}.{adjustment}.{industry}.{measure}",
        f"{name}, {adj_title.lower()}, {measure}",
        unit,
        frequency,
        enum,
        definition,
        f"ect-anzsic06-v1:{industry}:{measure}",
        f"ect:{industry}",
        source_url,
    ), expected


REQUIRED = tuple(
    f"ect.m.{adj}.{group}.value"
    for adj in ("actual", "sa", "trend")
    for group in ("retail", "core", "total")
) + ("ect.m.actual.total.count", "ect.m.actual.total.average")
REQUIRED += tuple(
    f"ect.m.{adj}.{industry}.value"
    for adj in ("actual", "sa", "trend")
    for industry, _ in INDUSTRIES.values()
)


def supported_definitions() -> dict[str, SeriesDef]:
    codes = [
        f"ECT{f}.S{group}{a}{i}{suffix}"
        for f in "MQ"
        for group, indices, adjustments, suffix in [
            ("19", "129WX", "AST", ""),
            ("19", "129", "S", "PC"),
            ("1G", "12345678", "AST", ""),
            ("29", "129WX", "A", ""),
        ]
        for a in adjustments
        for i in indices
    ] + [f"ECT{f}.S4A1V" for f in "MQ"]
    return {d.key: d for code in codes for d, _ in [identity(code)]}

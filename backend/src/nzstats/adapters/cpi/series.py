"""Explicit supported Stats NZ CPI identities. Anything else in the files is ignored or rejected."""

from __future__ import annotations

from dataclasses import dataclass

from nzstats.domain import Adjustment, Frequency, SeriesDef

SLUG = "consumers-price-index"
BASE_QUARTER = "2017-06"
BASE_VALUE = 1000.0
BASE_TEXT = "June 2017 quarter (=1000)"

INDEX_FILE, SA_FILE, TRADABLES_FILE = (
    "cpi_index_numbers",
    "cpi_seasonally_adjusted",
    "cpi_tradables",
)

# (code suffix, key slug, official Stats NZ name)
LEVEL1 = (
    ("01", "food", "Food"),
    ("02", "alcohol_tobacco", "Alcoholic beverages and tobacco"),
    ("03", "clothing_footwear", "Clothing and footwear"),
    ("04", "housing", "Housing and household utilities"),
    ("05", "household_contents", "Household contents and services"),
    ("06", "health", "Health"),
    ("07", "transport", "Transport"),
    ("08", "communication", "Communication"),
    ("09", "recreation_culture", "Recreation and culture"),
    ("10", "education", "Education"),
    ("11", "miscellaneous", "Miscellaneous goods and services"),
)
# Selected Level 2/3 series for housing, energy and food: (reference, slug, official name, level)
OPTIONAL = (
    ("CPIQ.SE9011", "fruit_vegetables", "Fruit and vegetables", 2),
    ("CPIQ.SE9012", "meat_poultry_fish", "Meat, poultry and fish", 2),
    ("CPIQ.SE9013", "grocery_food", "Grocery food", 2),
    ("CPIQ.SE9015", "restaurant_meals", "Restaurant meals and ready-to-eat food", 2),
    ("CPIQ.SE9041", "actual_rentals", "Actual rentals for housing", 2),
    ("CPIQ.SE904201", "purchase_of_housing", "Purchase of housing", 3),
    ("CPIQ.SE904401", "water_supply", "Water supply", 3),
    ("CPIQ.SE904403", "local_authority_rates", "Local authority rates and payments", 3),
    ("CPIQ.SE9045", "household_energy", "Household energy", 2),
    ("CPIQ.SE904501", "electricity", "Electricity", 3),
    ("CPIQ.SE904502", "gas", "Gas", 3),
    ("CPIQ.SE9072", "private_transport", "Private transport supplies and services", 2),
    ("CPIQ.SE907202", "petrol", "Petrol", 3),
)
# Official quarterly percentage-change measures that Stats NZ publishes only in the workbook
# (tables 10 and 11): (reference, slug, official name).
UNDERLYING = (
    ("SE9NS4000", "tm05", "Trimmed mean, 5 percent trim"),
    ("SE9NS4005", "tm10", "Trimmed mean, 10 percent trim"),
    ("SE9NS4010", "tm15", "Trimmed mean, 15 percent trim"),
    ("SE9NS4015", "tm20", "Trimmed mean, 20 percent trim"),
    ("SE9NS4020", "tm25", "Trimmed mean, 25 percent trim"),
    ("SE9NS4025", "tm30", "Trimmed mean, 30 percent trim"),
    ("SE9NS4100", "pct10", "Weighted 10th percentile"),
    ("SE9NS4105", "pct25", "Weighted 25th percentile"),
    ("SE9NS4110", "median", "Weighted median"),
    ("SE9NS4115", "pct75", "Weighted 75th percentile"),
    ("SE9NS4120", "pct90", "Weighted 90th percentile"),
)
# Contribution-chart group labels that differ from the CSV names.
CHART_ALIASES = {"Housing contents and services": "household_contents"}
TRADABLE_NAME, NON_TRADABLE_NAME = "Tradable All Groups", "Non-Tradable All Groups"
CROSS_CHECK = "CPIQ.SE9A"  # also published in the tradables file; never stored from there

LEVEL1_SLUGS = tuple(slug for _, slug, _ in LEVEL1)
CHART_GROUPS = {name: slug for _, slug, name in LEVEL1} | CHART_ALIASES


@dataclass(frozen=True)
class Expected:
    """What a CSV row for one series must say about itself."""

    fields: dict[str, str]
    group_tokens: tuple[str, ...]


@dataclass(frozen=True)
class _Spec:
    file_kind: str
    reference: str
    slug: str
    name: str
    adjustment: Adjustment
    group_tokens: tuple[str, ...]
    csv_name: str  # the name as the CSV writes it (differs from `name` for tradables)


def _specs() -> dict[tuple[str, str], _Spec]:
    nsa, sa = Adjustment.NONE, Adjustment.SEASONALLY_ADJUSTED
    out: dict[tuple[str, str], _Spec] = {}

    def add(kind, ref, slug, name, adj, tokens, csv_name=None):
        out[(kind, ref)] = _Spec(kind, ref, slug, name, adj, tokens, csv_name or name)

    add(INDEX_FILE, "CPIQ.SE9A", "all_groups", "All groups", nsa, ("All Groups",), "All groups")
    add(
        SA_FILE, "CPIQ.SE9SA", "all_groups", "All groups", sa, ("All Groups", "Seasonally adjusted")
    )
    for slug, ref, csv_name, name in (
        ("tradables", "SE9NS6000", TRADABLE_NAME, "Tradables"),
        ("non_tradables", "SE9NS6500", NON_TRADABLE_NAME, "Non-tradables"),
    ):
        add(TRADABLES_FILE, f"CPIQ.{ref}", slug, name, nsa, ("Tradable & Non-tradable",), csv_name)
        add(
            SA_FILE,
            f"CPIQ.SE9S{ref[3:]}",
            slug,
            name,
            sa,
            ("Tradable & Non-tradable", "Seasonally adjusted"),
            csv_name,
        )
    for code, slug, name in LEVEL1:
        add(INDEX_FILE, f"CPIQ.SE9{code}", slug, name, nsa, ("Level 1 Groups",))
        add(SA_FILE, f"CPIQ.SE9S{code}", slug, name, sa, ("Level 1 Groups", "Seasonally adjusted"))
    for ref, slug, name, level in OPTIONAL:
        add(INDEX_FILE, ref, slug, name, nsa, (f"Level {level}",))
    return out


_SPECS = _specs()
CORE_NSA = ("all_groups", "tradables", "non_tradables", *LEVEL1_SLUGS)
CORE_SA = ("all_groups", "tradables", "non_tradables")
CORE_KEYS = tuple(f"cpi.index.nsa.{s}" for s in CORE_NSA) + tuple(
    f"cpi.index.sa.{s}" for s in CORE_SA
)


def index_key(adjustment: Adjustment, slug: str) -> str:
    return f"cpi.index.{'sa' if adjustment is Adjustment.SEASONALLY_ADJUSTED else 'nsa'}.{slug}"


def contribution_key(horizon: str, slug: str) -> str:
    if horizon not in ("q", "a"):
        raise ValueError("horizon must be 'q' or 'a'")
    return f"cpi.contrib.{horizon}.{slug}"


def _index_def(spec: _Spec, source_url: str | None) -> SeriesDef:
    adj_text = (
        "seasonally adjusted" if spec.adjustment is Adjustment.SEASONALLY_ADJUSTED else "unadjusted"
    )
    definition = (
        f"Stats NZ CPI series {spec.reference}; {spec.name}; quarterly {adj_text} index, "
        f"base {BASE_TEXT}. Official percentage changes are calculated from the rounded "
        "published index. Status FINAL is final; REVISED is normalised to unknown and remains revisable."
    )
    return SeriesDef(
        index_key(spec.adjustment, spec.slug),
        f"{spec.name}, {adj_text} index",
        "index",
        Frequency.QUARTERLY,
        spec.adjustment,
        definition,
        f"cpi-v1:index:{spec.adjustment.value}:{spec.slug}",
        f"cpi:{spec.slug}",
        source_url,
    )


def identity(
    file_kind: str, reference: str, source_url: str | None = None
) -> tuple[SeriesDef, Expected] | None:
    spec = _SPECS.get((file_kind, reference))
    if spec is None:
        return None
    sa = spec.adjustment is Adjustment.SEASONALLY_ADJUSTED
    fields = {
        "UNITS": "Index",
        "Subject": "CPI",
        "Series_title_1": "Seasonally adjusted" if sa else spec.csv_name,
        "Series_title_2": spec.csv_name if sa else "NA",
    }
    return _index_def(spec, source_url), Expected(fields, spec.group_tokens)


def contribution_definition(horizon: str, slug: str, source_url: str | None = None) -> SeriesDef:
    name = next(n for _, s, n in LEVEL1 if s == slug)
    span = "previous quarter" if horizon == "q" else "same quarter of the previous year"
    return SeriesDef(
        contribution_key(horizon, slug),
        f"{name}, {'quarterly' if horizon == 'q' else 'annual'} percentage-point contribution",
        "pp",
        Frequency.QUARTERLY,
        Adjustment.NONE,
        f"Stats NZ published percentage-point contribution of {name} to the all-groups change from the "
        f"{span}, latest quarter of the release. Supplementary analytical information calculated from "
        "unrounded index numbers; groups sum to the headline change only approximately.",
        f"cpi-v1:contrib:{horizon}:{slug}",
        f"cpi:{slug}",
        source_url,
    )


def supported_definitions() -> dict[str, SeriesDef]:
    defs = {d.key: d for spec in _SPECS.values() for d in [_index_def(spec, None)]}
    for horizon in ("q", "a"):
        for slug in LEVEL1_SLUGS:
            d = contribution_definition(horizon, slug)
            defs[d.key] = d
    for _, slug, _ in UNDERLYING:
        d = underlying_definition(slug)
        defs[d.key] = d
    return defs


def underlying_key(slug: str) -> str:
    return f"cpi.underlying.{slug}"


def underlying_definition(slug: str, source_url: str | None = None) -> SeriesDef:
    ref, _, name = next(u for u in UNDERLYING if u[1] == slug)
    return SeriesDef(
        underlying_key(slug),
        f"{name}, quarterly percentage change",
        "percent",
        Frequency.QUARTERLY,
        Adjustment.NONE,
        f"Stats NZ official CPI series CPIQ.{ref} ({name}), percentage change from the previous quarter, "
        "published in the release workbook (tables 10 and 11) and calculated from unrounded index numbers. "
        "An official Stats NZ measure shown as published; the dashboard does not label any measure core inflation.",
        f"cpi-v1:underlying:{slug}",
        "cpi:underlying",
        source_url,
    )


_LEVELS = {slug: "Level 1 group" for slug in LEVEL1_SLUGS} | {
    slug: f"Level {level} {'subgroup' if level == 2 else 'class'}" for _, slug, _, level in OPTIONAL
}


def classification(slug: str) -> str:
    if slug == "all_groups":
        return "All groups"
    if slug in ("tradables", "non_tradables"):
        return "Tradability grouping"
    return _LEVELS[slug]


def source_reference(key: str) -> str | None:
    """The Stats NZ series reference (for example CPIQ.SE904) behind a stored index key."""
    for spec in _SPECS.values():
        if index_key(spec.adjustment, spec.slug) == key:
            return spec.reference
    return None

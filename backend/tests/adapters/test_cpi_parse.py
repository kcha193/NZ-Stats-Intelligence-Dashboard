from dataclasses import replace

import pytest

from nzstats.adapters.cpi.adapter import CpiAdapter
from nzstats.domain import Adjustment, ErrorClass, Frequency, IngestError, ObsStatus
from nzstats.pipeline.ingest import pick_downloads
from nzstats.sources.release_page import Chart, classify_download
from tests.cpi_support import edited, files, mutated, page

REQUIRED = CpiAdapter.required_downloads
ALL_NSA = '"CPIQ.SE9A","2026.06","1359","FINAL","Index","CPI","CPI All Groups for New Zealand","All groups","NA"'


def parse(source=None, pg=None):
    return CpiAdapter().parse(pg or page(), source or files())


def by_key(bundle):
    return {s.definition.key: s for s in bundle.series}


@pytest.fixture(scope="module")
def june():
    return by_key(parse())


def test_core_series_have_expected_identity_and_latest_values(june):
    all_groups = june["cpi.index.nsa.all_groups"]
    d = all_groups.definition
    assert (d.unit, d.frequency, d.adjustment) == ("index", Frequency.QUARTERLY, Adjustment.NONE)
    assert d.name == "All groups, unadjusted index"
    assert all_groups.observations[-1].period == "2026-06"
    assert all_groups.observations[-1].value == 1359.0
    assert june["cpi.index.nsa.tradables"].observations[-1].value == 1257.0
    assert june["cpi.index.nsa.non_tradables"].observations[-1].value == 1438.0
    sa = june["cpi.index.sa.all_groups"].definition
    assert sa.adjustment is Adjustment.SEASONALLY_ADJUSTED
    assert sa.definition_id != d.definition_id
    assert "June 2017 quarter (=1000)" in d.definition
    assert june["cpi.index.nsa.household_contents"].definition.name.startswith(
        "Household contents and services"
    )


def test_history_starts_at_the_first_unbroken_quarter(june):
    first = {k: s.observations[0].period for k, s in june.items() if ".index." in k}
    assert first["cpi.index.nsa.all_groups"] == "1925-09"
    assert first["cpi.index.nsa.tradables"] == "1999-06"
    assert first["cpi.index.sa.non_tradables"] == "2010-03"


def test_missing_values_are_dropped_never_zero(june):
    for series in june.values():
        assert all(o.value > 0 for o in series.observations if ".index." in o.series_key)
    food = june["cpi.index.nsa.food"].observations
    assert food[0].period == "1925-09"  # 0 and NA rows before the unbroken run are gone


def test_periods_and_status_are_normalised(june):
    obs = june["cpi.index.nsa.all_groups"].observations
    assert all(
        len(o.period) == 7 and o.period[4] == "-" and o.period[5:] in ("03", "06", "09", "12")
        for o in obs
    )
    assert {o.status for o in obs} == {ObsStatus.FINAL}
    assert {o.status for o in june["cpi.index.sa.tradables"].observations} <= {
        ObsStatus.FINAL,
        ObsStatus.UNKNOWN,
    }
    assert ObsStatus.UNKNOWN in {o.status for o in june["cpi.index.sa.tradables"].observations}


def test_bundle_series_counts(june):
    assert len([k for k in june if k.startswith("cpi.index.nsa.")]) == 3 + 11 + 13
    assert len([k for k in june if k.startswith("cpi.index.sa.")]) == 3 + 11
    assert len([k for k in june if k.startswith("cpi.contrib.")]) == 22
    assert CpiAdapter().parse(page(), files()).layout_version == "cpi-csv-v1"


@pytest.mark.parametrize(
    ("kind", "old", "new", "error"),
    [
        (
            "cpi_index_numbers",
            ALL_NSA,
            ALL_NSA.replace('"2026.06"', '"2026.05"'),
            ErrorClass.VALIDATION_FAILED,
        ),
        ("cpi_index_numbers", ALL_NSA, ALL_NSA + "\n" + ALL_NSA, ErrorClass.VALIDATION_FAILED),
        ("cpi_index_numbers", '"STATUS"', '"Status"', ErrorClass.LAYOUT_CHANGED),
        (
            "cpi_index_numbers",
            ALL_NSA,
            ALL_NSA.replace('"Index"', '"Percent"'),
            ErrorClass.VALIDATION_FAILED,
        ),
        (
            "cpi_index_numbers",
            ALL_NSA,
            ALL_NSA.replace('"All groups"', '"Everything"'),
            ErrorClass.VALIDATION_FAILED,
        ),
        (
            "cpi_index_numbers",
            ALL_NSA,
            ALL_NSA.replace('"FINAL"', '"DRAFT"'),
            ErrorClass.VALIDATION_FAILED,
        ),
        (
            "cpi_index_numbers",
            ALL_NSA,
            ALL_NSA.replace('"1359"', '"-4"'),
            ErrorClass.VALIDATION_FAILED,
        ),
        (
            "cpi_index_numbers",
            ALL_NSA,
            ALL_NSA
            + '\n"CPIQ.SE912","2026.06","1000","FINAL","Index","CPI","CPI Level 1 Groups for New Zealand","New group","NA"',
            ErrorClass.LAYOUT_CHANGED,
        ),
        (
            "cpi_tradables",
            '"CPIQ.SE9A","2026.06","1359"',
            '"CPIQ.SE9A","2026.06","1360"',
            ErrorClass.VALIDATION_FAILED,
        ),
    ],
)
def test_invalid_sources_are_rejected(kind, old, new, error):
    with pytest.raises(IngestError) as caught:
        parse(edited(files(), kind, old, new))
    assert caught.value.error_class is error


def test_unknown_lower_level_series_is_ignored(june):
    extra = '\n"CPIQ.SE9099999","2026.06","1000","FINAL","Index","CPI","CPI Level 3 Classes for New Zealand","Something new","NA"'
    other = by_key(parse(edited(files(), "cpi_index_numbers", ALL_NSA, ALL_NSA + extra)))
    assert set(other) == set(june)


def test_contributions_are_taken_as_published(june):
    q, a = june["cpi.contrib.q.transport"], june["cpi.contrib.a.housing"]
    assert [(o.period, o.value) for o in q.observations] == [("2026-06", 0.824)]
    assert a.observations[0].value == 1.066
    assert q.definition.unit == "pp"
    # The chart says "Housing contents and services"; the official CSV name is "Household contents…".
    assert june["cpi.contrib.q.household_contents"].observations[0].value == 0.019
    assert june["cpi.contrib.q.household_contents"].definition.name.startswith(
        "Household contents and services"
    )


def test_missing_contribution_charts_are_omitted():
    pg = page()
    kept = tuple(c for c in pg.charts if "point contribution" not in c.title)
    bundle = parse(pg=replace(pg, charts=kept))
    assert not [s for s in bundle.series if ".contrib." in s.definition.key]


def _with_chart(prefix, change):
    pg = page()
    charts = tuple(Chart(*change(c)) if c.title.startswith(prefix) else c for c in pg.charts)
    return replace(pg, charts=charts)


@pytest.mark.parametrize(
    "change",
    [
        lambda c: (c.title, c.csv.replace("Food,", "Foodz,", 1)),  # unknown group
        lambda c: (c.title.replace("June 2026", "March 2026"), c.csv),  # wrong quarter
        lambda c: (c.title, c.csv.replace("0.824", "NaN")),  # non-finite value
        lambda c: (c.title, c.csv + "\nPercentage point contribution,1,2,3"),  # extra row
    ],
)
def test_invalid_present_contribution_chart_fails(change):
    with pytest.raises(IngestError):
        parse(pg=_with_chart("Quarterly percentage point", change))


def test_source_title_and_reference_must_match_a_quarter_release():
    pg = replace(page(), title="Electronic card transactions: September 2026")
    with pytest.raises(IngestError):
        parse(pg=pg)
    with pytest.raises(IngestError):  # reference after publication (2026-07-21)
        parse(pg=replace(page(), title="Consumers price index: December 2026 quarter"))


@pytest.mark.parametrize(
    ("kind", "reference", "fields", "key"),
    [
        (
            "cpi_index_numbers",
            "CPIQ.SE9015",
            {"Series_title_1": "Restaurant meals and ready to eat food"},
            "restaurant_meals",
        ),
        ("cpi_index_numbers", "CPIQ.SE904501", {"Data_value": "-3"}, "electricity"),
        ("cpi_index_numbers", "CPIQ.SE907202", {"STATUS": "DRAFT"}, "petrol"),
        ("cpi_index_numbers", "CPIQ.SE9045", {"UNITS": "Percent"}, "household_energy"),
        ("cpi_seasonally_adjusted", "CPIQ.SE9S06", {"Series_title_2": "Health care"}, "health"),
    ],
)
def test_a_problem_in_an_optional_series_drops_it_with_a_warning(
    june, kind, reference, fields, key
):
    adjustment = "sa" if kind == "cpi_seasonally_adjusted" else "nsa"
    bundle = parse(mutated(files(), kind, reference, **fields))
    keys = {s.definition.key for s in bundle.series}
    assert f"cpi.index.{adjustment}.{key}" not in keys
    assert keys == set(june) - {f"cpi.index.{adjustment}.{key}"}  # nothing else is lost
    assert any(reference in w for w in bundle.warnings)


def test_core_series_problems_still_reject_the_bundle():
    with pytest.raises(IngestError):
        parse(
            mutated(files(), "cpi_index_numbers", "CPIQ.SE907", Series_title_1="Transport services")
        )


def test_series_cite_the_corrected_file_when_the_page_lists_both(june):
    """Ingestion fetches `-corrected` downloads; provenance must name the file the values came from."""
    pg = page()
    originals = {k: u for u in pg.download_urls if (k := classify_download(u)) in REQUIRED}
    corrected = {k: u.replace(".csv", "-corrected.csv") for k, u in originals.items()}
    others = tuple(u for u in pg.download_urls if u not in originals.values())
    # the uncorrected file is listed first, as in the real page
    urls = (*originals.values(), *corrected.values(), *others)
    assert pick_downloads(urls, REQUIRED) == corrected  # what ingestion actually fetches
    bundle = parse(pg=replace(pg, download_urls=urls))
    cited = {
        s.definition.source_url for s in bundle.series if s.definition.key.startswith("cpi.index.")
    }
    assert cited <= set(corrected.values()) and cited.isdisjoint(originals.values())
    assert (
        by_key(bundle)["cpi.index.nsa.all_groups"].definition.source_url
        == corrected["cpi_index_numbers"]
    )
    # the uncorrected listing alone still cites the original file
    assert june["cpi.index.nsa.all_groups"].definition.source_url == originals["cpi_index_numbers"]


PERCENT_ROW_LABELS = (
    "CPI all groups (quarterly)",
    "CPI all groups (annual)",
    "Tradeables (annual)",
    "Non-tradeables (annual)",
)


def _percent_row_edit(label, edit):
    """The release page with one published-percentage row rewritten by `edit(cells)`."""

    def change(chart):
        lines = chart.csv.split("\n")
        for n, line in enumerate(lines):
            if line.startswith(label + ","):
                ending = "\r" if line.endswith("\r") else ""  # keep the page's line endings
                lines[n] = ",".join(edit(line.removesuffix("\r").split(","))) + ending
        return chart.title, "\n".join(lines)

    pg = page()
    charts = tuple(
        Chart(*change(c)) if c.csv.startswith("Quarter,") and label in c.csv else c
        for c in pg.charts
    )
    return replace(pg, charts=charts)


@pytest.mark.parametrize("label", PERCENT_ROW_LABELS)
@pytest.mark.parametrize(
    "edit",
    [
        lambda cells: cells[:-1],  # the newest cell is missing: row narrower than its header
        lambda cells: [*cells[:-1], ""],  # the newest cell is blank
        lambda cells: [*cells[:-1], "NaN"],  # not a finite percentage
        lambda cells: [*cells, "9.9"],  # wider than the header
    ],
    ids=["missing_newest", "blank_newest", "nan_newest", "extra_cell"],
)
def test_a_malformed_published_percentage_row_rejects_the_release(label, edit):
    with pytest.raises(IngestError):
        parse(pg=_percent_row_edit(label, edit))


@pytest.mark.parametrize("label", PERCENT_ROW_LABELS)
def test_complete_published_percentage_rows_still_reconcile(label):
    assert parse(pg=_percent_row_edit(label, lambda cells: cells))

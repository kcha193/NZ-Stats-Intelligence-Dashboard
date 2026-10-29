import pytest

from nzstats.sources.calendar import make_release_key, parse_title
from nzstats.sources.release_page import classify_download, parse_release_page, pick_downloads
from tests.conftest import fixture_text

BASE = "https://www.stats.govt.nz"
DL = (
    BASE
    + "/assets/Uploads/Gross-domestic-product/Gross-domestic-product-June-2026-quarter/Download-data/"
)


@pytest.mark.parametrize("month", ["2026-06", "2026-03"])
def test_gdp_downloads_are_classified(month):
    page = parse_release_page(fixture_text(f"gdp_{month}_page.html"), BASE)
    label = {"2026-06": "june", "2026-03": "march"}[month]
    kinds = {u.rsplit("/", 1)[-1]: classify_download(u) for u in page.download_urls}
    stem = f"gross-domestic-product-{label}-2026-quarter"
    assert kinds == {
        f"{stem}.xlsx": "workbook",
        f"{stem}.csv": "gdp_csv",
        f"{stem}-current-price-income-and-expenditure.xlsx": "workbook",
        f"{stem}-supplementary-tables.xlsx": "workbook",
        f"{stem}-visualisation.csv": None,
    }


def test_corrected_gdp_csv_is_classified_and_wins():
    original = f"{DL}gross-domestic-product-june-2026-quarter.csv"
    corrected = f"{DL}gross-domestic-product-june-2026-quarter-corrected.csv"
    assert classify_download(corrected) == "gdp_csv"
    assert pick_downloads([original, corrected], ["gdp_csv"]) == {"gdp_csv": corrected}


def test_revised_republication_wins_like_corrected():
    original = f"{DL}gross-domestic-product-june-2026-quarter.csv"
    revised = f"{DL}gross-domestic-product-june-2026-quarter-revised.csv"
    assert classify_download(revised) == "gdp_csv"
    assert pick_downloads([original, revised], ["gdp_csv"]) == {"gdp_csv": revised}


@pytest.mark.parametrize(
    "name",
    [
        "gross-domestic-product-june-2026-quarter-visualisation.csv",
        "gross-domestic-product-june-2026.csv",  # not a quarterly release
        "gross-domestic-product-june-2026-quarter.zip",
        "regional-gross-domestic-product-year-ended-march-2025.csv",
    ],
)
def test_other_gdp_files_are_not_the_main_csv(name):
    assert classify_download(DL + name) != "gdp_csv"


def test_gdp_title_maps_to_release():
    parts = parse_title("Gross domestic product: June 2026 quarter")
    assert (parts.series_slug, parts.reference_period) == ("gross-domestic-product", "2026-06")
    assert (
        make_release_key("Gross domestic product: June 2026 quarter")
        == "gross-domestic-product:june 2026 quarter"
    )


@pytest.mark.parametrize(
    ("month", "zip_name"),
    [
        ("2026-06", "labour-market-statistics-june-2026-quarter.zip"),
        ("2026-03", "labour-market-statistics-march-2026-quarter-revised.zip"),
    ],
)
def test_labour_market_zip_is_classified_on_both_real_pages(month, zip_name):
    page = parse_release_page(fixture_text(f"labour_{month}_page.html"), BASE)
    kinds = {u.rsplit("/", 1)[-1]: classify_download(u) for u in page.download_urls}
    assert kinds[zip_name] == "labour_zip"
    assert [k for k in kinds.values() if k == "labour_zip"] == ["labour_zip"]
    assert all(k == "workbook" for n, k in kinds.items() if n.endswith(".xlsx"))


def test_revised_labour_zip_wins_over_the_original():
    original = DL + "labour-market-statistics-march-2026-quarter.zip"
    revised = DL + "labour-market-statistics-march-2026-quarter-revised.zip"
    assert pick_downloads([original, revised], ["labour_zip"]) == {"labour_zip": revised}


@pytest.mark.parametrize(
    "name",
    [
        "labour-market-statistics-june-2026.zip",
        "labour-market-statistics-june-2026-quarter.csv",
        "employment-indicators-june-2026.zip",
    ],
)
def test_other_files_are_not_the_labour_zip(name):
    assert classify_download(DL + name) != "labour_zip"


def test_labour_title_maps_to_release():
    parts = parse_title("Labour market statistics: June 2026 quarter")
    assert (parts.series_slug, parts.reference_period) == ("labour-market-statistics", "2026-06")

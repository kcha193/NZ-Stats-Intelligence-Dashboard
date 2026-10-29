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

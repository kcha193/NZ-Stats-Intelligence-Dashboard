import pytest

from nzstats.sources.calendar import make_release_key, parse_title
from nzstats.sources.release_page import classify_download, parse_release_page
from tests.conftest import fixture_text

BASE = "https://www.stats.govt.nz"
DL = (
    BASE
    + "/assets/Uploads/Consumers-price-index/Consumers-price-index-June-2026-quarter/Download-data/"
)


def test_june_2026_downloads_are_classified():
    page = parse_release_page(fixture_text("cpi_2026-06_page.html"), BASE)
    kinds = {u.rsplit("/", 1)[-1]: classify_download(u) for u in page.download_urls}
    assert kinds == {
        "consumers-price-index-june-2026-quarter.xlsx": "workbook",
        "consumers-price-index-june-2026-quarter-infoshare-data.csv": None,
        "consumers-price-index-june-2026-quarter-seasonally-adjusted.csv": "cpi_seasonally_adjusted",
        "consumers-price-index-june-2026-quarter-index-numbers.csv": "cpi_index_numbers",
        "consumers-price-index-june-2026-quarter-tradeables-and-non-tradeables.csv": "cpi_tradables",
        "consumers-price-index-june-2026-quarter-central-and-local-government-charges.xlsx": None,
    }


@pytest.mark.parametrize(
    "spelling", ["tradeables-and-non-tradeables", "tradables-and-non-tradables"]
)
def test_tradables_spelling_variants(spelling):
    url = f"{DL}consumers-price-index-june-2026-quarter-{spelling}.csv"
    assert classify_download(url) == "cpi_tradables"


def test_existing_kinds_are_unchanged():
    assert (
        classify_download(BASE + "/x/electronic-card-transactions-september-2026.zip") == "ect_zip"
    )
    assert classify_download(BASE + "/x/international-migration-age-sex-June-2026.csv") == "age_sex"
    assert classify_download(BASE + "/x/other-report.xlsx") == "workbook"


def test_september_quarter_title_maps_to_cpi_release():
    parts = parse_title("Consumers price index: September 2026 quarter")
    assert (parts.series_slug, parts.period_label, parts.reference_period) == (
        "consumers-price-index",
        "September 2026 quarter",
        "2026-09",
    )
    assert (
        make_release_key("Consumers price index: September 2026 quarter")
        == "consumers-price-index:september 2026 quarter"
    )

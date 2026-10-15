import pytest

from nzstats.clock import to_utc_iso
from nzstats.domain import ErrorClass, IngestError
from nzstats.sources.release_page import classify_download, parse_release_page
from tests.conftest import fixture_text

BASE = "https://www.stats.govt.nz"


@pytest.fixture(scope="module")
def page():
    return parse_release_page(fixture_text("im_2026-07_page.html"), BASE)


def test_basic_fields(page) -> None:
    assert page.title == "International migration: July 2026"
    assert to_utc_iso(page.published_at) == "2026-09-13T22:45:00Z"  # 14 Sep 10:45 NZST
    assert page.headline and "net migration" in page.headline.lower()


def test_charts_are_extracted_with_csv(page) -> None:
    chart = page.chart_starting_with("Estimated migration by direction, rolling year")
    assert chart is not None
    first_line = chart.csv.splitlines()[0]
    assert first_line.startswith('"Year ended"') and "Jul-2026" in first_line
    assert not chart.csv.startswith("﻿")
    monthly = page.chart_starting_with("Estimated migrant arrivals and migrant departures, monthly")
    assert monthly is not None


def test_downloads_are_absolute_and_deduplicated(page) -> None:
    assert len(page.download_urls) == len(set(page.download_urls))
    assert all(u.startswith(f"{BASE}/assets/Uploads/") for u in page.download_urls)
    kinds = {classify_download(u) for u in page.download_urls}
    assert {"age_sex", "citizenship_visa_country", "workbook"} <= kinds


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("/a/international-migration-july-2026-estimated-migration-by-age-and-sex.csv", "age_sex"),
        ("/a/international-migration-july-2024-estimated-migration-by-age-sex.csv", "age_sex"),
        (
            "/a/international-migration-july-2026-citizenship-by-visa-by-country-of-last-permanent-residence.csv",
            "citizenship_visa_country",
        ),
        ("/a/international-migration-july-2026.xlsx", "workbook"),
        ("/a/estimated-migration-by-direction-monthly.png", None),
        ("/a/something-else.csv", None),
    ],
)
def test_classify_download(url, kind) -> None:
    assert classify_download(url) == kind


def test_page_without_data_blob_is_layout_changed() -> None:
    with pytest.raises(IngestError) as e:
        parse_release_page("<html><body>hello</body></html>", BASE)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED

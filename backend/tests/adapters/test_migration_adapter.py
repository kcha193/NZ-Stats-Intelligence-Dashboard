import dataclasses

import pytest

from nzstats.adapters.migration.adapter import MigrationAdapter
from nzstats.domain import ErrorClass, IngestError
from nzstats.sources.release_page import parse_release_page
from tests.conftest import fixture_bytes, fixture_text

BASE = "https://www.stats.govt.nz"


@pytest.fixture(scope="module")
def page():
    return parse_release_page(fixture_text("im_2026-07_page.html"), BASE)


@pytest.fixture(scope="module")
def files():
    return {
        "age_sex": fixture_bytes("im_2026-07_age_sex.csv"),
        "citizenship_visa_country": fixture_bytes("im_2026-07_citizenship_country.csv"),
    }


def test_bundle_contains_all_required_series(page, files) -> None:
    bundle = MigrationAdapter().parse(page, files)
    keys = {p.definition.key for p in bundle.series}
    assert {
        "mig.m.arrivals",
        "mig.m.departures",
        "mig.m.net",
        "mig.ry.arrivals",
        "mig.ry.departures",
        "mig.ry.net",
        "mig.ry.net.nz",
        "mig.ry.net.nonnz",
        "mig.m.arrivals.nz",
        "mig.m.arrivals.nonnz",
    } <= keys
    assert len(keys) == len(bundle.series), "series keys must be unique"
    assert bundle.layout_version == "migration-csv-v1"


def test_adapter_declares_its_inputs() -> None:
    a = MigrationAdapter()
    assert a.series_slug == "international-migration"
    assert set(a.required_downloads) == {"age_sex", "citizenship_visa_country"}
    assert "mig.m.net" in a.previous_keys


def test_missing_chart_is_layout_changed(page, files) -> None:
    without = dataclasses.replace(page, charts=())
    with pytest.raises(IngestError) as e:
        MigrationAdapter().parse(without, files)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


# --- regressions found by the real-site integration check (chart titles drift between releases) --
# Titles below are copied from real Stats NZ release pages; only the CSV content is stable.


def _retitle(page, mapping):
    charts = tuple(
        dataclasses.replace(c, title=mapping.get(i, c.title)) for i, c in enumerate(page.charts)
    )
    return dataclasses.replace(page, charts=charts)


def _chart_index(page, text):
    return next(i for i, c in enumerate(page.charts) if text in c.title)


@pytest.mark.parametrize(
    ("direction_title", "citizenship_title"),
    [
        (
            " Estimated migration by direction, rolling year ended December 2001–November 2025 ",
            " Estimated migration by citizenship, rolling year ended December 2001–November 2024",
        ),
        (
            "Estimated migration by direction, rolling ye Dec 2001-March 2025",
            "Estimated migration by citizenship",
        ),
        ("Estimated migration by direction D", "Est migration by citizenship, roll"),
        (
            "Estimated migration by direction, rolling years ended December 2001–August 2025",
            "Estimated migration by citizenship, years ended December 2001–August 2025",
        ),
        (
            "Estimated migration by direction, rolling year ended December 2001–November 2025",
            "Estimates from August 2024 onwards are provisional and subject to revision.",
        ),
        (
            "Estimates from October 2024 onwards are provisional and subject to revision. ",
            "Estimated migration by citizenship, rolling year ended December 2001–January 2026",
        ),
    ],
)
def test_rolling_charts_are_found_by_content_not_title(
    page, files, direction_title, citizenship_title
) -> None:
    drifted = _retitle(
        page,
        {
            _chart_index(page, "by direction, rolling year"): direction_title,
            _chart_index(page, "by citizenship, rolling year"): citizenship_title,
        },
    )
    keys = {p.definition.key for p in MigrationAdapter().parse(drifted, files).series}
    assert {"mig.ry.net", "mig.ry.net.nz", "mig.ry.net.nonnz"} <= keys


def test_release_without_citizenship_chart_still_ingests_the_rest(page, files) -> None:
    """September 2025 genuinely published no year-ended citizenship chart."""
    idx = _chart_index(page, "by citizenship, rolling year")
    without = dataclasses.replace(
        page, charts=tuple(c for i, c in enumerate(page.charts) if i != idx)
    )
    adapter = MigrationAdapter()
    bundle = adapter.parse(without, files)
    keys = {p.definition.key for p in bundle.series}
    assert "mig.ry.net" in keys and "mig.ry.net.nz" not in keys and "mig.ry.net.nonnz" not in keys
    findings = adapter.validate(bundle, reference_period="2026-07", previous={})
    assert [f for f in findings if f.severity == "error"] == []
    assert any("citizenship" in f.message.lower() for f in findings if f.severity == "warning")


def test_release_without_direction_chart_is_still_layout_changed(page, files) -> None:
    idx = _chart_index(page, "by direction, rolling year")
    without = dataclasses.replace(
        page, charts=tuple(c for i, c in enumerate(page.charts) if i != idx)
    )
    with pytest.raises(IngestError) as e:
        MigrationAdapter().parse(without, files)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED

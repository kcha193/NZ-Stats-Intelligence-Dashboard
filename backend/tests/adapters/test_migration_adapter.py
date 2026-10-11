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

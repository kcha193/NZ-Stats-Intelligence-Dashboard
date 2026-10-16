"""F01: optional published series must be as trustworthy as required headline totals."""

from dataclasses import replace

import pytest

from nzstats.adapters.migration.adapter import MigrationAdapter
from nzstats.domain import Adjustment, Frequency
from nzstats.sources.release_page import parse_release_page
from nzstats.validate.rules import validate_migration
from tests.conftest import fixture_bytes, fixture_text


@pytest.fixture(scope="module")
def official_bundle():
    return MigrationAdapter().parse(
        parse_release_page(fixture_text("im_2026-07_page.html"), "https://www.stats.govt.nz"),
        {
            "age_sex": fixture_bytes("im_2026-07_age_sex.csv"),
            "citizenship_visa_country": fixture_bytes("im_2026-07_citizenship_country.csv"),
        },
    )


def shifted(bundle, key, period, delta=10000):
    return replace(
        bundle,
        series=tuple(
            replace(
                ps,
                observations=tuple(
                    replace(o, value=o.value + delta) if o.period == period else o
                    for o in ps.observations
                ),
            )
            if ps.definition.key == key
            else ps
            for ps in bundle.series
        ),
    )


def errors(bundle):
    return {
        f.rule
        for f in validate_migration(bundle, reference_period="2026-07", previous={})
        if f.severity == "error"
    }


@pytest.mark.parametrize("period", ["2025-07", "2026-07"])
@pytest.mark.parametrize("direction", ["arrivals", "departures", "net"])
@pytest.mark.parametrize("citizenship", ["nz", "nonnz"])
def test_corrupt_annual_citizenship_is_rejected(official_bundle, period, direction, citizenship):
    bad = shifted(official_bundle, f"mig.ry.{direction}.{citizenship}", period)
    assert "citizenship_annual_sum" in errors(bad)


def test_offsetting_net_corruption_cannot_hide_behind_a_correct_total(official_bundle):
    bad = shifted(official_bundle, "mig.ry.net.nz", "2026-07")
    bad = shifted(bad, "mig.ry.net.nonnz", "2026-07", -10000)
    assert "citizenship_net_identity" in errors(bad)


def test_citizenship_annual_arrivals_match_twelve_month_window(official_bundle):
    bad = shifted(official_bundle, "mig.ry.arrivals.nz", "2026-07")
    bad = shifted(bad, "mig.ry.arrivals.nonnz", "2026-07", -10000)
    assert "citizenship_rolling" in errors(bad)


@pytest.mark.parametrize(
    "metadata",
    [
        {"unit": "thousands of people"},
        {"frequency": Frequency.MONTHLY},
        {"adjustment": Adjustment.SEASONALLY_ADJUSTED},
        {"definition_id": "different.measure"},
    ],
)
def test_incompatible_citizenship_measure_is_rejected(official_bundle, metadata):
    bad = replace(
        official_bundle,
        series=tuple(
            replace(ps, definition=replace(ps.definition, **metadata))
            if ps.definition.key == "mig.ry.net.nz"
            else ps
            for ps in official_bundle.series
        ),
    )
    assert "citizenship_compatibility" in errors(bad)


def test_negative_standard_error_is_rejected(official_bundle):
    bad = replace(
        official_bundle,
        series=tuple(
            replace(
                ps, observations=(*ps.observations[:-1], replace(ps.observations[-1], std_error=-1))
            )
            if ps.definition.key == "mig.m.net"
            else ps
            for ps in official_bundle.series
        ),
    )
    assert "nonnegative" in errors(bad)


def test_offsetting_negative_country_count_is_rejected(official_bundle):
    countries = [
        ps
        for ps in official_bundle.series
        if ps.definition.category == "migration:country" and ps.observations[-1].period == "2026-07"
    ]
    first, second = countries[:2]
    delta = first.observations[-1].value + 100
    bad = shifted(official_bundle, first.definition.key, "2026-07", -delta)
    bad = shifted(bad, second.definition.key, "2026-07", delta)
    assert "nonnegative" in errors(bad)


def test_duplicate_observation_cannot_be_silently_overwritten(official_bundle):
    bad = replace(
        official_bundle,
        series=tuple(
            replace(
                ps, observations=(*ps.observations, replace(ps.observations[-1], value=999999999))
            )
            if ps.definition.key == "mig.ry.net.nz"
            else ps
            for ps in official_bundle.series
        ),
    )
    assert "duplicate" in errors(bad)


def test_official_rounding_and_negative_net_values_remain_valid(official_bundle):
    assert errors(official_bundle) == set()


@pytest.mark.parametrize(
    "direction,value",
    [("net", 999999999), ("net", -999999999), ("arrivals", 999999999), ("departures", 999999999)],
)
def test_one_optional_component_cannot_exceed_total_flow_bounds(official_bundle, direction, value):
    key = f"mig.ry.{direction}.nz"
    kept = tuple(
        ps
        for ps in official_bundle.series
        if not ps.definition.key.startswith("mig.ry.")
        or ps.definition.key.count(".") == 2
        or ps.definition.key == key
    )
    bad = replace(official_bundle, series=kept)
    ps = next(ps for ps in kept if ps.definition.key == key)
    bad = shifted(bad, key, "2026-07", value - ps.observations[-1].value)
    assert "citizenship_bounds" in errors(bad)


def test_country_name_starting_with_net_does_not_allow_negative_counts(official_bundle):
    key = "mig.m.arrivals.country.netherlands"
    ps = next(ps for ps in official_bundle.series if ps.definition.key == key)
    delta = ps.observations[-1].value + 100
    bad = shifted(official_bundle, key, "2026-07", -delta)
    bad = shifted(bad, "mig.m.arrivals.country.afghanistan", "2026-07", delta)
    assert "nonnegative" in errors(bad)

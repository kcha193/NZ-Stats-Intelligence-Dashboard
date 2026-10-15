"""A new vintage must not silently drop history the previous vintage held (PR #1 review threads
#4280291084, #4280291091). Real files start every monthly series in 2001-01 and every year-ended
series in 2001-12 (the first derivable period) in both the June and July 2026 releases."""

import dataclasses

import pytest

from nzstats.adapters.migration.adapter import MigrationAdapter
from nzstats.domain import Point
from nzstats.validate.rules import OPTIONAL_ROLLING_CITIZENSHIP, REQUIRED
from tests.validate.test_rules import _rules, good_bundle, run


def _previous(bundle) -> dict[str, dict[str, Point]]:
    return {
        ps.definition.key: {o.period: Point(o.period, o.value, o.status) for o in ps.observations}
        for ps in bundle.series
    }


def _keep(bundle, key: str, periods: int):
    """`bundle` with only the latest `periods` observations of `key`."""
    ps = next(p for p in bundle.series if p.definition.key == key)
    kept = dataclasses.replace(
        ps, observations=tuple(sorted(ps.observations, key=lambda o: o.period)[-periods:])
    )
    return dataclasses.replace(
        bundle, series=tuple(kept if p.definition.key == key else p for p in bundle.series)
    )


def _sorted_obs(bundle, key: str) -> list[str]:
    ps = next(p for p in bundle.series if p.definition.key == key)
    return sorted(o.period for o in ps.observations)


@pytest.mark.parametrize("key", ["mig.m.net", "mig.m.arrivals.nz"])
def test_monthly_history_cut_to_the_latest_twelve_months_is_rejected(key) -> None:
    full = good_bundle()
    findings = run(_keep(full, key, 12), previous=_previous(full))
    assert "coverage" in _rules(findings)


def test_year_ended_chart_reduced_to_its_latest_column_is_rejected() -> None:
    full = good_bundle()
    findings = run(_keep(full, "mig.ry.net", 1), previous=_previous(full))
    assert "coverage" in _rules(findings)


def test_optional_citizenship_series_cannot_shrink_either() -> None:
    full = good_bundle()
    longer = _previous(full)
    longer["mig.ry.net.nz"] = {
        p: Point(p, -100.0, o.status)
        for p, o in longer["mig.ry.net"].items()  # an earlier release covered more periods
    }
    assert _sorted_obs(full, "mig.ry.net.nz") != sorted(longer["mig.ry.net.nz"])
    assert "coverage" in _rules(run(full, previous=longer))


def test_unchanged_or_longer_coverage_passes() -> None:
    full = good_bundle()
    assert "coverage" not in _rules(run(full, previous=_previous(full)))
    shorter = _previous(_keep(full, "mig.m.net", 13))
    assert "coverage" not in _rules(run(full, previous=shorter))


def test_first_release_without_previous_vintage_passes() -> None:
    assert "coverage" not in _rules(run(good_bundle(), previous={}))


def test_adapter_loads_the_previous_vintage_of_every_validated_series() -> None:
    keys = set(MigrationAdapter().previous_keys)
    assert set(REQUIRED) | set(OPTIONAL_ROLLING_CITIZENSHIP) <= keys

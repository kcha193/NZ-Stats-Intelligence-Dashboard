"""Historical rolling totals and the required citizenship series (PR #1 review threads)."""

import dataclasses

import pytest

from nzstats.adapters.migration import series as S
from nzstats.domain import Observation, ObsStatus
from nzstats.validate.rules import CITIZENSHIP_TOLERANCE, ROLLING_TOLERANCE
from tests.validate.test_rules import PERIODS, _ps, _rules, good_bundle, run

LATEST = PERIODS[-1]


def _series(bundle, key):
    return next(p for p in bundle.series if p.definition.key == key)


def _shift(bundle, key: str, deltas: dict[str, float]):
    """Return a bundle with `key`'s observations moved by `deltas` (period -> delta)."""
    ps = _series(bundle, key)
    obs = tuple(
        dataclasses.replace(o, value=o.value + deltas.get(o.period, 0.0)) for o in ps.observations
    )
    shifted = dataclasses.replace(ps, observations=obs)
    return dataclasses.replace(
        bundle, series=tuple(shifted if p.definition.key == key else p for p in bundle.series)
    )


def _messages(findings, rule):
    return [f.message for f in findings if f.rule == rule and f.severity == "error"]


# -- Issue A: every derivable rolling total ---------------------------------------------------


@pytest.mark.parametrize("direction", ["arrivals", "departures", "net"])
def test_corrupt_historical_rolling_value_with_correct_latest_fails(direction) -> None:
    key = f"mig.ry.{direction}"
    assert _series(good_bundle(), key).observations[-1].period == LATEST
    bundle = _shift(good_bundle(), key, {"2025-09": 1000.0})
    msgs = _messages(run(bundle), "rolling_check")
    assert len(msgs) == 1
    assert direction in msgs[0]
    assert "2025-09" in msgs[0]


def test_every_corrupt_historical_value_is_reported() -> None:
    bundle = _shift(good_bundle(), "mig.ry.arrivals", {"2025-08": 50.0, "2025-12": -80.0})
    bundle = _shift(bundle, "mig.ry.net", {"2026-03": 500.0})
    msgs = _messages(run(bundle), "rolling_check")
    text = " ".join(msgs)
    for period in ("2025-08", "2025-12", "2026-03"):
        assert period in text
    assert "arrivals" in text and "net" in text
    assert "departures" not in text


def test_rolling_failure_names_published_derived_and_difference() -> None:
    bundle = _shift(good_bundle(), "mig.ry.departures", {"2025-10": 40.0})
    (msg,) = _messages(run(bundle), "rolling_check")
    published = _series(bundle, "mig.ry.departures")
    got = next(o.value for o in published.observations if o.period == "2025-10")
    assert f"{got:g}" in msg
    assert f"{got - 40.0:g}" in msg
    assert "40" in msg


@pytest.mark.parametrize("period", ["2025-07", "2025-11", LATEST])
def test_rolling_tolerance_applies_to_every_period(period) -> None:
    inside = _shift(good_bundle(), "mig.ry.net", {period: ROLLING_TOLERANCE})
    outside = _shift(good_bundle(), "mig.ry.net", {period: ROLLING_TOLERANCE + 1})
    assert "rolling_check" not in _rules(run(inside))
    assert "rolling_check" in _rules(run(outside))


def test_published_periods_without_monthly_history_are_not_false_positives() -> None:
    # The monthly series starts 2024-08, so year-ended 2024-12 has no complete window: it cannot be
    # checked, whatever its value, and must not be reported.
    ps = _series(good_bundle(), "mig.ry.arrivals")
    early = Observation("mig.ry.arrivals", "2024-12", 123.0, ObsStatus.FINAL)
    bundle = good_bundle(
        **{"mig.ry.arrivals": dataclasses.replace(ps, observations=(early, *ps.observations))}
    )
    assert _rules(run(bundle)) == set()


def test_latest_rolling_period_must_still_be_derivable() -> None:
    ps = _series(good_bundle(), "mig.ry.arrivals")
    ahead = Observation("mig.ry.arrivals", "2026-08", 1.0, ObsStatus.FINAL)
    bundle = good_bundle(
        **{"mig.ry.arrivals": dataclasses.replace(ps, observations=(*ps.observations, ahead))}
    )
    assert "rolling_check" in _rules(run(bundle, reference="2026-08"))


def test_fully_consistent_rolling_history_passes() -> None:
    assert "rolling_check" not in _rules(run())


# -- Issue B: required citizenship series ---------------------------------------------------


def _cit(key: str, values: dict[str, float]):
    return {key: _ps(S.citizenship_monthly_def(key.rsplit(".", 1)[1]), values)}


def _cit_values(bundle, key):
    return {o.period: o.value for o in _series(bundle, key).observations}


@pytest.mark.parametrize("key", ["mig.m.arrivals.nz", "mig.m.arrivals.nonnz"])
def test_missing_latest_citizenship_observation_fails(key) -> None:
    values = _cit_values(good_bundle(), key)
    del values[LATEST]
    findings = run(good_bundle(**_cit(key, values)))
    msgs = _messages(findings, "latest_period")
    assert any(key in m for m in msgs)


@pytest.mark.parametrize("key", ["mig.m.arrivals.nz", "mig.m.arrivals.nonnz"])
def test_historical_gap_in_citizenship_series_fails(key) -> None:
    values = _cit_values(good_bundle(), key)
    del values["2025-03"]
    msgs = _messages(run(good_bundle(**_cit(key, values))), "continuity")
    assert any(key in m and "2025-03" in m for m in msgs)


@pytest.mark.parametrize("key", ["mig.m.arrivals.nz", "mig.m.arrivals.nonnz"])
def test_short_citizenship_history_fails(key) -> None:
    values = {p: v for p, v in _cit_values(good_bundle(), key).items() if p >= "2026-03"}
    msgs = _messages(run(good_bundle(**_cit(key, values))), "history")
    assert any(key in m for m in msgs)


def test_citizenship_must_reconcile_with_total_arrivals_in_every_month() -> None:
    values = _cit_values(good_bundle(), "mig.m.arrivals.nz")
    values["2025-05"] += CITIZENSHIP_TOLERANCE + 1  # historical month, latest untouched
    msgs = _messages(run(good_bundle(**_cit("mig.m.arrivals.nz", values))), "citizenship_sum")
    assert len(msgs) == 1
    assert "2025-05" in msgs[0]


def test_citizenship_reconciliation_reports_every_bad_month() -> None:
    values = _cit_values(good_bundle(), "mig.m.arrivals.nonnz")
    for p in ("2024-09", "2025-05", LATEST):
        values[p] -= 500.0
    (msg,) = _messages(run(good_bundle(**_cit("mig.m.arrivals.nonnz", values))), "citizenship_sum")
    assert all(p in msg for p in ("2024-09", "2025-05", LATEST))


def test_citizenship_rounding_differences_within_tolerance_pass() -> None:
    nz = _cit_values(good_bundle(), "mig.m.arrivals.nz")
    nonnz = _cit_values(good_bundle(), "mig.m.arrivals.nonnz")
    nz["2025-05"] += 1.0  # observed real rounding is at most 1
    nonnz["2025-06"] -= CITIZENSHIP_TOLERANCE  # boundary
    bundle = good_bundle(**_cit("mig.m.arrivals.nz", nz), **_cit("mig.m.arrivals.nonnz", nonnz))
    assert _rules(run(bundle)) == set()


def test_valid_complete_citizenship_data_passes() -> None:
    assert _rules(run()) == set()


def test_missing_optional_rolling_citizenship_stays_a_warning() -> None:
    base = good_bundle()
    bundle = dataclasses.replace(
        base,
        series=tuple(
            p for p in base.series if p.definition.key not in ("mig.ry.net.nz", "mig.ry.net.nonnz")
        ),
    )
    findings = run(bundle)
    assert _rules(findings) == set()
    warned = {f.message for f in findings if f.rule == "optional_series"}
    assert len(warned) == 2
    assert all(f.severity == "warning" for f in findings if f.rule == "optional_series")


# -- standard errors are persisted and served as JSON, so they must be finite too (#4279007203) ---


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_standard_error_is_rejected(bad) -> None:
    ps = _series(good_bundle(), "mig.m.net")
    obs = tuple(
        dataclasses.replace(o, std_error=bad) if o.period == LATEST else o for o in ps.observations
    )
    bundle = good_bundle(**{"mig.m.net": dataclasses.replace(ps, observations=obs)})
    findings = run(bundle)
    assert "finite" in _rules(findings)
    message = next(f.message for f in findings if f.rule == "finite")
    assert "mig.m.net" in message and "standard error" in message and LATEST in message


def test_finite_and_absent_standard_errors_pass() -> None:
    ps = _series(good_bundle(), "mig.m.net")
    obs = tuple(
        dataclasses.replace(o, std_error=None if i % 2 else 12.5)
        for i, o in enumerate(ps.observations)
    )
    bundle = good_bundle(**{"mig.m.net": dataclasses.replace(ps, observations=obs)})
    assert "finite" not in _rules(run(bundle))

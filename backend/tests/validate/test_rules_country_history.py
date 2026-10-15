"""Country reconciliation for every stored month, not only the latest (PR #1 review thread
PRRT_kwDOVEW9cs6sm_kM): `rank_countries` sums up to 36 months plus a prior window of the same length.
"""

import dataclasses

import pytest

from nzstats.adapters.migration import series as S
from nzstats.validate.rules import COUNTRY_TOLERANCE_ABS, COUNTRY_TOLERANCE_REL
from tests.validate.test_rules import PERIODS, _ps, _rules, good_bundle, run

LATEST = PERIODS[-1]
COVERAGE = PERIODS[-14:]  # country file holds 2025-06..2026-07; earlier months are not covered
BAD = COVERAGE[3]
UNALLOCATED = 400.0  # 4% of a month: well outside the country tolerance, so it must be counted
SPARSE_FROM = COVERAGE[6]


def _total(period: str) -> float:
    return 10000.0 + PERIODS.index(period) * 10


def _tolerance(period: str) -> float:
    return max(COUNTRY_TOLERANCE_ABS, COUNTRY_TOLERANCE_REL * _total(period))


def _country_series() -> dict:
    """Countries A, B (dense), C (sparse: absent before SPARSE_FROM), D (explicit zeros),
    'Not Stated' and a region. Every month reconciles exactly to total arrivals."""
    a, b, c, d, ns, region = {}, {}, {}, {}, {}, {}
    for p in COVERAGE:
        total = _total(p)
        a[p] = round(total * 0.6)
        c_val = 50.0 if p >= SPARSE_FROM else None
        if c_val is not None:
            c[p] = c_val
        d[p] = 0.0
        ns[p] = UNALLOCATED
        b[p] = total - a[p] - UNALLOCATED - (c_val or 0.0)
        region[p] = total * 0.7
    return {
        "mig.m.arrivals.country.a": _ps(S.country_def("A", "country"), a),
        "mig.m.arrivals.country.b": _ps(S.country_def("B", "country"), b),
        "mig.m.arrivals.country.c": _ps(S.country_def("C", "country"), c),
        "mig.m.arrivals.country.d": _ps(S.country_def("D", "country"), d),
        "mig.m.arrivals.country.not-stated": _ps(S.country_def("Not Stated", "unallocated"), ns),
        "mig.m.arrivals.region.asia": _ps(S.country_def("Asia", "region"), region),
    }


def _bundle(**overrides):
    return good_bundle(**{**_country_series(), **overrides})


def _edit(bundle, key: str, *, add: dict[str, float] | None = None, drop: tuple[str, ...] = ()):
    """Bundle with `key`'s observations shifted by `add` (period -> delta) and `drop` removed."""
    add = add or {}
    out = []
    for ps in bundle.series:
        if ps.definition.key == key:
            obs = tuple(
                dataclasses.replace(o, value=o.value + add.get(o.period, 0.0))
                for o in ps.observations
                if o.period not in drop
            )
            ps = dataclasses.replace(ps, observations=obs)
        out.append(ps)
    return dataclasses.replace(bundle, series=tuple(out))


def _messages(findings, rule):
    return [f.message for f in findings if f.rule == rule and f.severity == "error"]


def test_valid_sparse_country_history_passes() -> None:
    assert _rules(run(_bundle())) == set()


def test_legitimate_zero_valued_country_observations_pass() -> None:
    bundle = _bundle()
    assert any(
        o.value == 0.0
        for ps in bundle.series
        if ps.definition.key.endswith("country.d")
        for o in ps.observations
    )
    assert "country_sum" not in _rules(run(bundle))


def test_corrupted_historical_country_value_with_valid_latest_month_fails() -> None:
    bad = _edit(_bundle(), "mig.m.arrivals.country.a", add={BAD: 500.0})
    findings = run(bad)
    assert "country_sum" in _rules(findings)
    (message,) = _messages(findings, "country_sum")
    assert BAD in message and LATEST not in message
    assert "+500" in message  # reconciliation difference is reported


def test_missing_historical_country_row_that_breaks_reconciliation_fails() -> None:
    bad = _edit(_bundle(), "mig.m.arrivals.country.a", drop=(BAD,))
    findings = run(bad)
    (message,) = _messages(findings, "country_sum")
    assert BAD in message
    assert f"{-round(_total(BAD) * 0.6):+g}" in message


def test_a_whole_missing_month_is_reported_separately_from_a_missing_row() -> None:
    bundle = _bundle()
    for key in (
        "mig.m.arrivals.country.a",
        "mig.m.arrivals.country.b",
        "mig.m.arrivals.country.c",
        "mig.m.arrivals.country.d",
        "mig.m.arrivals.country.not-stated",
    ):
        bundle = _edit(bundle, key, drop=(BAD,))
    findings = run(bundle)
    assert "country_month_missing" in _rules(findings)
    assert "country_sum" not in _rules(findings)
    (message,) = _messages(findings, "country_month_missing")
    assert BAD in message


def test_missing_latest_month_of_country_data_still_fails() -> None:
    bundle = _bundle()
    for key in list(_country_series()):
        if "region" not in key:
            bundle = _edit(bundle, key, drop=(LATEST,))
    assert "country_month_missing" in _rules(run(bundle))


def test_months_before_the_country_coverage_are_not_treated_as_zero() -> None:
    bundle = _bundle()
    first_covered = min(
        o.period
        for ps in bundle.series
        if "country.a" in ps.definition.key
        for o in ps.observations
    )
    assert first_covered == COVERAGE[0] and PERIODS[0] < first_covered
    assert _rules(run(bundle)) == set()


def test_sparse_country_absent_before_its_first_row_is_not_an_error() -> None:
    bundle = _bundle()
    c = next(ps for ps in bundle.series if ps.definition.key.endswith("country.c"))
    assert min(o.period for o in c.observations) == SPARSE_FROM > COVERAGE[0]
    assert "country_sum" not in _rules(run(bundle))


def test_unallocated_observations_count_towards_every_month() -> None:
    bad = _edit(_bundle(), "mig.m.arrivals.country.not-stated", drop=(BAD,))
    assert UNALLOCATED > _tolerance(BAD)
    assert BAD in _messages(run(bad), "country_sum")[0]


def test_regional_aggregates_are_excluded_in_historical_months() -> None:
    huge = _edit(_bundle(), "mig.m.arrivals.region.asia", add={BAD: 999999.0})
    assert _rules(run(huge)) == set()


def test_historical_difference_at_the_tolerance_passes_and_just_above_fails() -> None:
    tol = _tolerance(BAD)
    at = _edit(_bundle(), "mig.m.arrivals.country.a", add={BAD: tol})
    over = _edit(_bundle(), "mig.m.arrivals.country.a", add={BAD: tol + 1})
    under = _edit(_bundle(), "mig.m.arrivals.country.a", add={BAD: -tol})
    assert "country_sum" not in _rules(run(at))
    assert "country_sum" not in _rules(run(under))
    assert "country_sum" in _rules(run(over))


def test_every_bad_historical_month_is_reported() -> None:
    months = (COVERAGE[1], COVERAGE[4], COVERAGE[8])
    bad = _edit(_bundle(), "mig.m.arrivals.country.a", add={m: 700.0 for m in months})
    (message,) = _messages(run(bad), "country_sum")
    assert all(m in message for m in months)
    assert "3 months" in message


@pytest.mark.parametrize("period", [COVERAGE[0], COVERAGE[-2]])
def test_first_and_penultimate_covered_months_are_checked(period) -> None:
    bad = _edit(_bundle(), "mig.m.arrivals.country.a", add={period: 700.0})
    assert period in _messages(run(bad), "country_sum")[0]

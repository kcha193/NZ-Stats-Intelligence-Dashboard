import dataclasses
import math

import pytest

from nzstats.adapters.base import ParsedBundle, ParsedSeries
from nzstats.adapters.migration import series as S
from nzstats.domain import Observation, ObsStatus, Point
from nzstats.stats.periods import month_range
from nzstats.validate.rules import validate_migration

PERIODS = month_range("2024-08", "2026-07")  # 24 months


def _ps(definition, values: dict[str, float], status=ObsStatus.FINAL) -> ParsedSeries:
    return ParsedSeries(
        definition,
        tuple(Observation(definition.key, p, v, status) for p, v in values.items()),
    )


def good_bundle(**overrides) -> ParsedBundle:
    """Tiny internally consistent bundle (test input, never production data)."""
    arr = {p: 10000.0 + i * 10 for i, p in enumerate(PERIODS)}
    dep = {p: 8000.0 + i * 5 for i, p in enumerate(PERIODS)}
    net = {p: arr[p] - dep[p] for p in PERIODS}
    ry = {}
    for name, series in (("arrivals", arr), ("departures", dep), ("net", net)):
        ry[name] = {
            PERIODS[i]: sum(series[p] for p in PERIODS[i - 11 : i + 1]) for i in range(11, 24)
        }
    nz = {p: arr[p] * 0.3 for p in PERIODS}
    nonnz = {p: arr[p] * 0.7 for p in PERIODS}
    latest = PERIODS[-1]
    a_total = arr[latest]
    series = {
        "mig.m.arrivals": _ps(S.monthly_def("arrivals"), arr),
        "mig.m.departures": _ps(S.monthly_def("departures"), dep),
        "mig.m.net": _ps(S.monthly_def("net"), net),
        "mig.ry.arrivals": _ps(S.rolling_def("arrivals"), ry["arrivals"]),
        "mig.ry.departures": _ps(S.rolling_def("departures"), ry["departures"]),
        "mig.ry.net": _ps(S.rolling_def("net"), ry["net"]),
        "mig.ry.net.nz": _ps(S.rolling_def("net", "nz"), {latest: -100.0}),
        "mig.ry.net.nonnz": _ps(S.rolling_def("net", "nonnz"), {latest: 500.0}),
        "mig.m.arrivals.nz": _ps(S.citizenship_monthly_def("nz"), nz),
        "mig.m.arrivals.nonnz": _ps(S.citizenship_monthly_def("nonnz"), nonnz),
        "mig.m.arrivals.country.a": _ps(
            S.country_def("A", "country"), {latest: round(a_total * 0.6)}
        ),
        "mig.m.arrivals.country.b": _ps(
            S.country_def("B", "country"), {latest: a_total - round(a_total * 0.6)}
        ),
        "mig.m.arrivals.region.asia": _ps(S.country_def("Asia", "region"), {latest: 1.0}),
    }
    series.update(overrides)
    return ParsedBundle("test", tuple(series.values()))


def _rules(findings, severity="error"):
    return {f.rule for f in findings if f.severity == severity}


def run(bundle=None, reference="2026-07", previous=None):
    return validate_migration(
        bundle or good_bundle(), reference_period=reference, previous=previous or {}
    )


def test_consistent_bundle_has_no_errors() -> None:
    assert _rules(run()) == set()


def test_missing_required_series() -> None:
    b = good_bundle()
    b = dataclasses.replace(
        b, series=tuple(p for p in b.series if p.definition.key != "mig.ry.net")
    )
    assert "required_series" in _rules(run(b))


def test_gap_in_monthly_history() -> None:
    values = {p: 1.0 for p in PERIODS if p != "2025-03"}
    b = good_bundle(**{"mig.m.departures": _ps(S.monthly_def("departures"), values)})
    assert "continuity" in _rules(run(b))


@pytest.mark.parametrize(
    ("reference", "expect_error"), [("2026-07", False), ("2026-08", True), (None, False)]
)
def test_latest_period_must_match_release(reference, expect_error) -> None:
    assert ("latest_period" in _rules(run(reference=reference))) is expect_error


def test_net_identity_tolerance() -> None:
    arr = {p: 10000.0 + i * 10 for i, p in enumerate(PERIODS)}
    dep = {p: 8000.0 + i * 5 for i, p in enumerate(PERIODS)}
    ok = {p: arr[p] - dep[p] + (1 if p == "2025-01" else 0) for p in PERIODS}
    bad = {p: arr[p] - dep[p] + (3 if p == "2025-01" else 0) for p in PERIODS}
    assert "net_identity" not in _rules(
        run(good_bundle(**{"mig.m.net": _ps(S.monthly_def("net"), ok)}))
    )
    assert "net_identity" in _rules(
        run(good_bundle(**{"mig.m.net": _ps(S.monthly_def("net"), bad)}))
    )


def test_rolling_published_must_match_derived() -> None:
    base = good_bundle()
    ry = next(p for p in base.series if p.definition.key == "mig.ry.net")
    latest = ry.observations[-1]

    def shifted(delta: float) -> ParsedBundle:
        obs = ry.observations[:-1] + (dataclasses.replace(latest, value=latest.value + delta),)
        return good_bundle(**{"mig.ry.net": dataclasses.replace(ry, observations=obs)})

    assert "rolling_check" not in _rules(run(shifted(5.0)))
    assert "rolling_check" in _rules(run(shifted(6.0)))


def test_non_finite_values_rejected() -> None:
    values = {p: 1.0 for p in PERIODS}
    values["2026-07"] = math.nan
    b = good_bundle(**{"mig.m.arrivals": _ps(S.monthly_def("arrivals"), values)})
    assert "finite" in _rules(run(b))


def test_implausible_revisions_vs_previous_vintage() -> None:
    b = good_bundle()
    arr = next(p for p in b.series if p.definition.key == "mig.m.arrivals")
    halved = {o.period: Point(o.period, o.value * 0.5, ObsStatus.FINAL) for o in arr.observations}
    assert "revision_plausibility" in _rules(run(b, previous={"mig.m.arrivals": halved}))
    modest = {o.period: Point(o.period, o.value * 0.97, ObsStatus.FINAL) for o in arr.observations}
    assert "revision_plausibility" not in _rules(run(b, previous={"mig.m.arrivals": modest}))


def test_first_release_without_previous_is_fine() -> None:
    assert "revision_plausibility" not in _rules(run(previous={}))


def test_country_sum_must_reconcile_with_total() -> None:
    b = good_bundle()
    latest = PERIODS[-1]
    bad = good_bundle(
        **{"mig.m.arrivals.country.b": _ps(S.country_def("B", "country"), {latest: 1.0})}
    )
    assert "country_sum" not in _rules(run(b))
    assert "country_sum" in _rules(run(bad))


def test_regions_are_excluded_from_country_sum() -> None:
    latest = PERIODS[-1]
    huge_region = good_bundle(
        **{"mig.m.arrivals.region.asia": _ps(S.country_def("Asia", "region"), {latest: 999999.0})}
    )
    assert "country_sum" not in _rules(run(huge_region))


def test_overlong_provisional_window_is_only_a_warning() -> None:
    arr = {p: 10000.0 + i * 10 for i, p in enumerate(PERIODS)}
    dep = {p: 8000.0 + i * 5 for i, p in enumerate(PERIODS)}
    net = {p: arr[p] - dep[p] for p in PERIODS}
    prov = good_bundle(
        **{
            "mig.m.net": ParsedSeries(
                S.monthly_def("net"),
                tuple(
                    Observation("mig.m.net", p, v, ObsStatus.PROVISIONAL) for p, v in net.items()
                ),
            )
        }
    )
    findings = run(prov)
    assert "provisional_window" in _rules(findings, "warning")
    assert "provisional_window" not in _rules(findings, "error")


# --- PR #1 review (PRRT_kwDOVEW9cs6st5Jz, PRRT_kwDOVEW9cs6st5J7) ---------------------------------------


def test_a_bundle_with_no_country_observations_is_rejected() -> None:
    # A layout change that renames every TOTAL place row leaves the citizenship totals parseable but
    # yields no country series; accepting it would replace last-known-good country data with nothing.
    b = good_bundle()
    b = dataclasses.replace(
        b,
        series=tuple(p for p in b.series if p.definition.category != "migration:country"),
    )
    assert "country_missing" in _rules(run(b))


def test_a_gap_inside_a_year_ended_series_is_rejected() -> None:
    # A blank cell drops that month from the published series; the rolling check only looks at months
    # that remain, so the lost month (still derivable from the monthly data) must be caught here.
    b = good_bundle()
    arrivals = next(p for p in b.series if p.definition.key == "mig.ry.arrivals")
    kept = {o.period: o.value for o in arrivals.observations if o.period != PERIODS[16]}
    b = good_bundle(**{"mig.ry.arrivals": _ps(S.rolling_def("arrivals"), kept)})
    findings = run(b)
    assert "continuity" in _rules(findings)
    assert any("mig.ry.arrivals" in f.message for f in findings if f.rule == "continuity")

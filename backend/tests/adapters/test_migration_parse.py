import pandas as pd
import pytest

from nzstats.adapters.migration import series as S
from nzstats.adapters.migration.parse import (
    REGIONS,
    parse_age_sex_csv,
    parse_citizenship_country_csv,
    parse_wide_chart,
    with_rolling_status,
)
from nzstats.domain import ErrorClass, IngestError, ObsStatus
from nzstats.sources.release_page import parse_release_page
from nzstats.stats.periods import month_range
from tests.conftest import FIXTURES, fixture_bytes, fixture_text

BASE = "https://www.stats.govt.nz"


@pytest.fixture(scope="module")
def age_sex():
    return {p.definition.key: p for p in parse_age_sex_csv(fixture_bytes("im_2026-07_age_sex.csv"))}


@pytest.fixture(scope="module")
def page():
    return parse_release_page(fixture_text("im_2026-07_page.html"), BASE)


def _obs(ps, period):
    return next(o for o in ps.observations if o.period == period)


def test_monthly_totals_have_expected_keys_and_contiguous_history(age_sex) -> None:
    assert set(age_sex) == {"mig.m.arrivals", "mig.m.departures", "mig.m.net"}
    periods = [o.period for o in age_sex["mig.m.net"].observations]
    assert periods[0] == "2001-01" and periods[-1] == "2026-07"
    assert periods == month_range("2001-01", "2026-07")


def test_monthly_spot_values_are_real(age_sex) -> None:
    jul = {k: _obs(age_sex[k], "2026-07") for k in age_sex}
    assert (
        jul["mig.m.arrivals"].value,
        jul["mig.m.departures"].value,
        jul["mig.m.net"].value,
    ) == (13893.0, 8722.0, 5170.0)
    assert (jul["mig.m.arrivals"].std_error, jul["mig.m.net"].std_error) == (434.0, 545.0)
    assert jul["mig.m.net"].status is ObsStatus.PROVISIONAL
    assert jul["mig.m.net"].released_in == "2026-07"
    mar2020 = _obs(age_sex["mig.m.arrivals"], "2020-03")
    assert (mar2020.value, mar2020.status, mar2020.released_in) == (
        16243.0,
        ObsStatus.FINAL,
        "2021-07",
    )


def test_only_total_total_rows_are_used() -> None:
    df = pd.read_csv(FIXTURES / "im_2026-07_age_sex.csv")
    assert (df["sex"] != "TOTAL").any(), "fixture must include non-total rows to test filtering"
    expected = len(df[(df["sex"] == "TOTAL") & (df["age"] == "TOTAL")])
    parsed = parse_age_sex_csv(fixture_bytes("im_2026-07_age_sex.csv"))
    assert sum(len(p.observations) for p in parsed) == expected


def _mutate(name: str, fn) -> bytes:
    df = pd.read_csv(FIXTURES / name)
    return fn(df).to_csv(index=False, quoting=1).encode()


def test_missing_column_is_layout_changed() -> None:
    data = _mutate("im_2026-07_age_sex.csv", lambda d: d.drop(columns=["status"]))
    with pytest.raises(IngestError) as e:
        parse_age_sex_csv(data)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_unknown_status_is_layout_changed() -> None:
    def fn(d):
        d = d.copy()
        d.loc[d.index[0], "status"] = "Estimated"
        return d

    with pytest.raises(IngestError) as e:
        parse_age_sex_csv(_mutate("im_2026-07_age_sex.csv", fn))
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_conflicting_duplicate_period_is_layout_changed() -> None:
    def fn(d):
        total = d[(d.sex == "TOTAL") & (d.age == "TOTAL") & (d.direction == "Net")].head(1).copy()
        total["estimate"] = (
            total["estimate"] + 1
        )  # same period, different value: cannot be collapsed
        return pd.concat([d, total])

    with pytest.raises(IngestError) as e:
        parse_age_sex_csv(_mutate("im_2026-07_age_sex.csv", fn))
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


@pytest.fixture(scope="module")
def cit():
    data = fixture_bytes("im_2026-07_citizenship_country.csv")
    return {p.definition.key: p for p in parse_citizenship_country_csv(data, country_window=13)}


def test_citizenship_monthly_arrivals_reconcile_with_total(cit, age_sex) -> None:
    nz, nonnz = cit["mig.m.arrivals.nz"], cit["mig.m.arrivals.nonnz"]
    assert nz.observations[-1].period == "2026-07" and len(nz.observations) >= 300
    total = _obs(age_sex["mig.m.arrivals"], "2026-07").value
    assert abs(_obs(nz, "2026-07").value + _obs(nonnz, "2026-07").value - total) <= 2


def test_country_series_window_regions_and_unallocated(cit) -> None:
    india = cit["mig.m.arrivals.country.india"]
    assert india.definition.category == "migration:country"
    assert len(india.observations) <= 13
    assert india.observations[-1].period == "2026-07"
    assert _obs(india, "2026-06").value == 1510.0
    asia = cit["mig.m.arrivals.region.asia"]
    assert asia.definition.category == "migration:region" and _obs(asia, "2026-06").value == 5843.0
    ns = cit["mig.m.arrivals.country.not-stated"]
    assert ns.definition.category == "migration:unallocated"
    assert "mig.m.arrivals.country.total" not in cit
    assert {"Asia", "Europe"} <= REGIONS


def test_wide_chart_rolling_by_direction(page) -> None:
    chart = page.chart_starting_with("Estimated migration by direction, rolling year")
    parsed = {p.definition.key: p for p in parse_wide_chart(chart.csv, S.G1_LABELS)}
    assert set(parsed) == {"mig.ry.arrivals", "mig.ry.departures", "mig.ry.net"}
    last = {k: p.observations[-1] for k, p in parsed.items()}
    assert last["mig.ry.arrivals"].period == "2026-07"
    assert (
        last["mig.ry.arrivals"].value,
        last["mig.ry.departures"].value,
        last["mig.ry.net"].value,
    ) == (134434.0, 114084.0, 20350.0)
    assert parsed["mig.ry.net"].observations[0].period == "2001-12"
    assert parsed["mig.ry.net"].definition.frequency.value == "rolling_annual"


def test_wide_chart_rolling_by_citizenship(page) -> None:
    chart = page.chart_starting_with("Estimated migration by citizenship, rolling year")
    parsed = {p.definition.key: p for p in parse_wide_chart(chart.csv, S.G3_LABELS)}
    assert len(parsed) == 6
    assert parsed["mig.ry.net.nz"].observations[-1].value == -38335.0
    assert parsed["mig.ry.net.nonnz"].observations[-1].value == 58685.0
    assert parsed["mig.ry.arrivals.nz"].observations[-1].value == 26631.0


def test_wide_chart_missing_label_is_layout_changed(page) -> None:
    chart = page.chart_starting_with("Estimated migration by direction, rolling year")
    mapping = dict(S.G1_LABELS)
    mapping["Something new"] = S.rolling_def("net", "nz")
    with pytest.raises(IngestError) as e:
        parse_wide_chart(chart.csv, mapping)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_wide_chart_bad_header_is_layout_changed() -> None:
    with pytest.raises(IngestError):
        parse_wide_chart(
            '"Year ended","not-a-date"\n"Net migration",5\n',
            {"Net migration": S.rolling_def("net")},
        )


def test_rolling_status_follows_monthly_provisional_window(age_sex, page) -> None:
    chart = page.chart_starting_with("Estimated migration by direction, rolling year")
    net = next(
        p for p in parse_wide_chart(chart.csv, S.G1_LABELS) if p.definition.key == "mig.ry.net"
    )
    monthly = {o.period: o.status for o in age_sex["mig.m.net"].observations}
    out = {o.period: o.status for o in with_rolling_status(net, monthly).observations}
    assert out["2025-03"] is ObsStatus.FINAL  # months 2024-04..2025-03 all final
    assert out["2025-04"] is ObsStatus.PROVISIONAL  # includes provisional 2025-04
    assert out["2026-07"] is ObsStatus.PROVISIONAL
    assert out["2001-12"] is ObsStatus.FINAL


# --- regressions found by the real-site integration check (June 2024 release file) -------------


def test_exact_duplicate_rows_are_collapsed_not_summed() -> None:
    """Stats NZ's June 2024 file repeats some identical aggregate rows 2 or 3 times.

    The repeated value equals the official chart value (Sep 2022 arrivals: 12,561), so collapsing is
    right and summing would triple it.
    """
    series = {
        p.definition.key: p
        for p in parse_age_sex_csv(fixture_bytes("im_2024-06_age_sex_duplicate_rows_excerpt.csv"))
    }
    arrivals = {o.period: o.value for o in series["mig.m.arrivals"].observations}
    assert arrivals["2022-09"] == 12561
    assert arrivals["2022-08"] == 10198
    periods = [o.period for o in series["mig.m.arrivals"].observations]
    assert len(periods) == len(set(periods))


def test_conflicting_duplicate_periods_are_still_rejected() -> None:
    header = "year_month,month_of_release,passenger_type,direction,sex,age,estimate,standard_error,status\n"
    row = "2022-09,2024-01,Long-term migrant,Arrivals,TOTAL,TOTAL,{},0,Final\n"
    data = (header + row.format(12561) + row.format(99999)).encode()
    with pytest.raises(IngestError) as e:
        parse_age_sex_csv(data)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_unreadable_csv_error_does_not_echo_parser_text(caplog) -> None:
    bad = b"year_month,estimate\n2026-01,UPSTREAM-SECRET-\x00\xff"
    with pytest.raises(IngestError) as e:
        parse_age_sex_csv(bad)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED
    assert "UPSTREAM-SECRET" not in str(e.value)


@pytest.mark.parametrize("extra", [",999\n", ",1\n"])
def test_duplicate_chart_series_labels_are_rejected(extra) -> None:
    # Even identical rows must not conceal a changed upstream layout.
    data = "Year ended,Jul-2026\nNet migration,1\nNet migration" + extra
    with pytest.raises(IngestError, match="duplicate"):
        parse_wide_chart(data, {"Net migration": S.rolling_def("net")})


@pytest.mark.parametrize(
    "data",
    [
        "Year ended,Jul-2026,Jul-2026\nNet migration,1,2\n",
        "Year ended,Jul-2026\nNet migration,1,2\n",
    ],
)
def test_duplicate_periods_or_extra_chart_cells_are_rejected(data) -> None:
    with pytest.raises(IngestError):
        parse_wide_chart(data, {"Net migration": S.rolling_def("net")})

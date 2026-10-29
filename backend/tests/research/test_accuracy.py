"""Phase 3D-B accuracy arithmetic, ranking gates and consensus, on hand-counted SYNTHETIC FIXTURE numbers.

The pure functions are tested against values worked out by hand in the comments; the end-to-end evaluation uses the
real Stats NZ CPI fixture releases for its actuals.
"""

from __future__ import annotations

import math

import pytest

from nzstats.research.accuracy import (
    MIN_FOR_RANKING,
    MIN_FOR_SUMMARY,
    band_of,
    error_stats,
    evaluate_forecasts,
    horizon_quarters,
    rank,
)
from nzstats.research.consensus import consensus
from nzstats.research.outcomes import CpiActuals
from tests.cpi_support import ingest_cpi

from .test_compare import claim


def test_error_statistics_match_hand_computation():
    # errors 0.5, -0.3, 0.2, -0.4: mean 0.0; MAE (0.5+0.3+0.2+0.4)/4 = 0.35;
    # RMSE sqrt((0.25+0.09+0.04+0.16)/4) = sqrt(0.135) = 0.367423...
    stats = error_stats([0.5, -0.3, 0.2, -0.4])
    assert stats.n == 4 and stats.sufficient
    assert stats.mean_error == pytest.approx(0.0, abs=1e-12)
    assert stats.mae == pytest.approx(0.35)
    assert stats.rmse == pytest.approx(math.sqrt(0.135), abs=1e-6)  # stored to 6 decimal places


def test_too_few_outcomes_give_counts_but_no_statistics():
    stats = error_stats([0.5, -0.3, 0.2])
    assert MIN_FOR_SUMMARY == 4
    assert stats.n == 3 and not stats.sufficient
    assert stats.mae is None and stats.rmse is None and stats.mean_error is None


@pytest.mark.parametrize(("published", "quarter", "h", "band"), [
    ("2026-08-13", "2026-09", 0, "h0"),     # published in the September quarter, for it: a nowcast
    ("2026-10-05", "2026-09", -1, "h0"),    # after the quarter ended, before the release
    ("2026-08-13", "2026-12", 1, "h1_2"),
    ("2026-08-13", "2027-06", 3, "h3_4"),
    ("2026-02-01", "2027-03", 4, "h3_4"),
    ("2026-02-01", "2027-12", 7, "h5_8"),
    ("2025-01-15", "2027-06", 9, "h9"),
])  # fmt: skip
def test_horizon_in_quarters_and_bands(published, quarter, h, band):
    assert horizon_quarters(published, quarter) == h
    assert band_of(h) == band


def cell(inst, quarter, h, error):
    return {"institution": inst, "cell": (quarter, h), "error": error}


def test_ranking_needs_a_matched_sample_of_eight():
    assert MIN_FOR_RANKING == 8
    rows = [
        cell(i, f"20{20 + q // 4}-{(q % 4 + 1) * 3:02d}", 2, e)
        for q in range(7)
        for i, e in (("a", 0.1), ("b", 0.4))
    ]
    out = rank(rows)
    assert not out.available and "Only 7 targets were" in out.reason and "8" in out.reason
    assert "Only 1 target was" in rank([cell(i, "2020-03", 2, 0.1) for i in "ab"]).reason


def test_ranking_uses_only_cells_every_institution_forecast():
    rows = [
        cell(i, f"20{20 + q // 4}-{(q % 4 + 1) * 3:02d}", 2, e)
        for q in range(8)
        for i, e in (("a", 0.1), ("b", -0.4))
    ]
    rows += [cell("a", "2030-03", 2, 5.0)]  # only a forecast this target: must not count against a
    out = rank(rows)
    assert out.available and out.matched_cells == 8
    assert [(e.institution, e.n, e.mae) for e in out.entries] == [
        ("a", 8, pytest.approx(0.1)),
        ("b", 8, pytest.approx(0.4)),
    ]


def test_a_single_institution_is_never_ranked():
    rows = [cell("a", f"20{20 + q // 4}-{(q % 4 + 1) * 3:02d}", 2, 0.1) for q in range(12)]
    out = rank(rows)
    assert not out.available and "two" in out.reason


def test_consensus_is_descriptive_and_needs_two_institutions():
    groups = [
        claim(institution=k, summary_id=i, value=v, published_on="2026-08-13")
        for i, (k, v) in enumerate((("a", 2.0), ("b", 2.4), ("c", 2.2)), 1)
    ]
    (c,) = consensus(groups).groups
    # values 2.0, 2.2, 2.4: mean 2.2, median 2.2, range 0.4, sample sd 0.2.
    assert c.n == 3 and c.mean == pytest.approx(2.2) and c.median == pytest.approx(2.2)
    assert c.minimum == 2.0 and c.maximum == 2.4 and c.range == pytest.approx(0.4)
    assert c.std_dev == pytest.approx(0.2)
    assert c.outliers == [] and not c.outliers_assessed  # fewer than five
    assert "not" in c.note and "calibrated" in c.note
    one = consensus([claim(institution="a", value=2.0)])
    assert (
        one.groups[0].n == 1
        and one.groups[0].mean is None
        and one.groups[0].status == "insufficient"
    )


def test_consensus_flags_outliers_from_five_with_scaled_mad():
    # values 2.0, 2.1, 2.2, 2.3, 4.0: median 2.2; |dev| 0.2, 0.1, 0, 0.1, 1.8 -> MAD 0.1;
    # limit 3 x 1.4826 x 0.1 = 0.445; only 4.0 is beyond it.
    values = (("a", 2.0), ("b", 2.1), ("c", 2.2), ("d", 2.3), ("e", 4.0))
    (c,) = consensus(
        [claim(institution=k, summary_id=i, value=v) for i, (k, v) in enumerate(values, 1)]
    ).groups
    assert c.outliers_assessed and [o.key for o in c.outliers] == ["e"]


def test_consensus_excludes_scenarios_stale_and_aggregator_forecasts():
    out = consensus([
        claim(institution="a", summary_id=1, value=2.0, published_on="2026-08-13"),
        claim(institution="b", summary_id=2, value=2.4, published_on="2026-08-01"),
        claim(institution="c", summary_id=3, value=9.0, published_on="2026-08-13", scenario="Downside"),
        claim(institution="d", summary_id=4, value=2.2, published_on="2026-01-10"),  # > 180 days before the newest
        claim(institution="e", summary_id=5, value=2.3, published_on="2026-08-10",
              document_title="Consensus Forecasts, August 2026"),
    ])  # fmt: skip
    central = [g for g in out.groups if g.kind == "central"]
    (c,) = central
    assert c.n == 2 and sorted(x.key for x in c.contributors) == ["a", "b"]
    reasons = {x.forecast.institution.key: x.reason for x in c.excluded}
    assert "180 days" in reasons["d"] and "other forecasters" in reasons["e"]
    assert all(g.kind == "central" for g in out.groups)  # scenarios never form a baseline consensus


def test_consensus_takes_each_institutions_latest_vintage_once():
    out = consensus([
        claim(institution="a", summary_id=1, value=3.0, published_on="2026-05-01"),
        claim(institution="a", summary_id=2, value=2.0, published_on="2026-08-13"),
        claim(institution="b", summary_id=3, value=2.4, published_on="2026-08-13"),
    ])  # fmt: skip
    (c,) = out.groups
    assert c.n == 2 and c.mean == pytest.approx(2.2)


@pytest.fixture()
def cpi_actuals(rt, site):
    ingest_cpi(rt, site, "2025-12", "2026-03", "2026-06", "2026-09")
    # Simulated publication-day capture for scoring arithmetic; no historical provenance claim.
    rt.conn.execute(
        "UPDATE vintage SET captured_at = (SELECT published_at FROM release WHERE id = release_id)"
    )
    return CpiActuals(rt.conn)


def test_evaluation_matches_errors_against_first_published_actuals(cpi_actuals):
    out = evaluate_forecasts([
        # Annual CPI, June 2026 quarter: official 4.1. Error 3.5 - 4.1 = -0.6, horizon 2 quarters.
        claim(institution="a", summary_id=1, published_on="2025-12-10", horizon="year to June 2026", value=3.5),
        # Published after the June release (21 July 2026): look-ahead, excluded.
        claim(institution="b", summary_id=2, published_on="2026-07-21", horizon="year to June 2026", value=4.1),
        # December 2026 quarter is not released yet: pending.
        claim(institution="a", summary_id=3, published_on="2026-08-13", horizon="year to December 2026", value=3.0),
        # OCR has no official series here.
        claim(institution="a", summary_id=4, indicator="ocr", indicator_label="OCR", horizon="June 2026 quarter",
              value=3.0),
    ], cpi_actuals, indicator="cpi_inflation")  # fmt: skip
    assert out.state == "available"
    (matched,) = [e for e in out.evaluated if e.status == "matched"]
    assert matched.first.value == 4.1 and matched.error_first == pytest.approx(-0.6)
    assert matched.horizon_quarters == 2 and matched.band == "h1_2"
    (pending,) = [e for e in out.evaluated if e.status == "pending"]
    assert pending.target_quarter == "2026-12" and pending.first is None
    assert any("on or after" in x.reason for x in out.excluded)
    assert not any(
        x.forecast.indicator == "ocr" for x in out.excluded
    )  # other indicators are not in this view
    (summary,) = [s for s in out.summaries if s.institution.key == "a"]
    assert summary.n == 1 and summary.mae is None  # one outcome: insufficient
    assert out.rankings[0].available is False
    assert out.actuals_as_of.startswith("Consumers price index: September 2026")
    assert out.actuals_released_on == "2026-10-22"


def test_indicators_without_an_official_series_say_so(cpi_actuals):
    out = evaluate_forecasts([claim(indicator="gdp", indicator_label="Real GDP, annual average growth",
                                    horizon="year to March 2027", value=1.5)], cpi_actuals, indicator="gdp")  # fmt: skip
    assert out.state == "no_official_series" and out.evaluated == []


def test_nothing_to_evaluate_is_an_explicit_state(cpi_actuals):
    assert (
        evaluate_forecasts([], cpi_actuals, indicator="cpi_inflation").state
        == "nothing_to_evaluate"
    )


def test_scenarios_are_never_scored_against_the_outcome(cpi_actuals):
    out = evaluate_forecasts([
        claim(institution="a", summary_id=1, published_on="2025-12-10", horizon="year to June 2026", value=1.6,
              scenario="Downside"),
    ], cpi_actuals, indicator="cpi_inflation")  # fmt: skip
    assert out.evaluated == []
    (x,) = out.excluded
    assert "scenario" in x.reason.lower()


# Annual CPI per target quarter (Stats NZ): Dec 2025 3.1 (1327/1287), Mar 2026 3.1, Jun 2026 4.1, Sep 2026 3.7. Each
# target is forecast one quarter ahead (h1_2 band) by a latest vintage and an earlier one published in the same
# quarter, so both share an exact horizon and a ranking cell. (published_on, value)
LATEST_VINTAGE = {
    "year to December 2025": ("2025-08-15", 3.0),
    "year to March 2026": ("2025-11-15", 3.5),
    "year to June 2026": ("2026-02-15", 3.6),
    "year to September 2026": ("2026-05-15", 3.9),
}
EARLIER_VINTAGE = {
    "year to December 2025": ("2025-07-10", 9.0),
    "year to March 2026": ("2025-10-05", 9.0),
    "year to June 2026": ("2026-01-15", 9.0),
    "year to September 2026": ("2026-04-10", 9.0),
}


def vintages(horizons, *, earlier=True, institution="a"):
    rows = []
    for horizon in horizons:
        for table in (EARLIER_VINTAGE, LATEST_VINTAGE) if earlier else (LATEST_VINTAGE,):
            published_on, value = table[horizon]
            rows.append(claim(institution=institution, summary_id=len(rows) + 1, published_on=published_on,
                              horizon=horizon, value=value))  # fmt: skip
    return rows


def a_summary(out, institution="a"):
    (s,) = [s for s in out.summaries if s.institution.key == institution]
    return s


def test_four_vintages_of_one_quarter_are_one_outcome_not_four(cpi_actuals):
    june = "year to June 2026"
    forecasts = [
        claim(institution="a", summary_id=i, published_on=d, horizon=june, value=3.6)
        for i, d in enumerate(("2025-10-01", "2025-12-10", "2026-01-20", "2026-02-20"), start=1)
    ]
    out = evaluate_forecasts(forecasts, cpi_actuals, indicator="cpi_inflation")
    assert (
        len([e for e in out.evaluated if e.status == "matched"]) == 4
    )  # every vintage stays visible
    s = a_summary(out)
    assert s.n == 1 and not s.sufficient and s.mae is None


def test_three_distinct_outcomes_are_insufficient_however_many_vintages(cpi_actuals):
    horizons = list(LATEST_VINTAGE)[:3]
    out = evaluate_forecasts(vintages(horizons), cpi_actuals, indicator="cpi_inflation")
    assert len(out.evaluated) == 6
    s = a_summary(out)
    assert (s.band, s.n, s.sufficient, s.mae) == ("h1_2", 3, False, None)


def test_four_distinct_outcomes_are_scored_on_each_quarters_latest_vintage_only(cpi_actuals):
    out = evaluate_forecasts(vintages(list(LATEST_VINTAGE)), cpi_actuals, indicator="cpi_inflation")
    s = a_summary(out)
    # Errors from the latest vintage per quarter: 3.0-3.1, 3.5-3.1, 3.6-4.1, 3.9-3.7 = -0.1, 0.4, -0.5, 0.2.
    # (The 9.0 earlier vintages would give MAE above 5 if they were counted.)
    assert s.n == 4 and s.sufficient
    assert s.mean_error == pytest.approx(0.0) and s.mae == pytest.approx(0.3)
    assert s.rmse == pytest.approx(math.sqrt(0.115), abs=1e-6)


def test_the_selected_vintage_does_not_depend_on_input_order(cpi_actuals):
    forecasts = vintages(list(LATEST_VINTAGE))
    forward = evaluate_forecasts(forecasts, cpi_actuals, indicator="cpi_inflation")
    backward = evaluate_forecasts(forecasts[::-1], cpi_actuals, indicator="cpi_inflation")
    assert a_summary(forward) == a_summary(backward)


def test_vintages_of_a_quarter_in_different_bands_are_separate_samples(cpi_actuals):
    june = "year to June 2026"
    out = evaluate_forecasts([
        claim(institution="a", summary_id=1, published_on="2026-02-15", horizon=june, value=3.6),  # h1_2
        claim(institution="a", summary_id=2, published_on="2026-06-15", horizon=june, value=4.0),  # h0
    ], cpi_actuals, indicator="cpi_inflation")  # fmt: skip
    assert sorted((s.band, s.n) for s in out.summaries) == [("h0", 1), ("h1_2", 1)]


def test_ranking_counts_cells_not_vintages(cpi_actuals):
    forecasts = vintages(list(LATEST_VINTAGE)) + vintages(list(LATEST_VINTAGE), institution="b")
    for i, f in enumerate(forecasts, start=1):
        forecasts[i - 1] = f.model_copy(update={"summary_id": i})
    out = evaluate_forecasts(forecasts, cpi_actuals, indicator="cpi_inflation")
    (ranking,) = out.rankings
    assert len(out.evaluated) == 16
    assert ranking.matched_cells == 4 and not ranking.available  # four cells, not sixteen vintages

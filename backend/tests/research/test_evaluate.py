"""The evaluation harness: metric functions on hand-computed inputs, then the full synthetic set."""

from pathlib import Path

import pytest

from nzstats.research import evaluate as ev
from nzstats.research.contract import ForecastClaim, LlmLimits
from nzstats.research.providers import FakeProvider, Pricing

EVAL_SET = Path(__file__).parent / "eval_set"


def fc(indicator, horizon, value, unit="percent", scenario=None):
    return ForecastClaim(indicator=indicator, indicator_label=indicator, horizon=horizon, value=value,
                         unit=unit, direction="unclear", scenario=scenario,
                         evidence=[{"version_id": 1, "section_ordinal": 0, "quote": "placeholder text"}])  # fmt: skip


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [("year to March 2027", "Year to March 2027", True), ("2026/27", "year to June 2027", False),
     ("June 2027 year", "year to June 2027", True), ("March 2027 quarter", "year to March 2027", False),
     ("2027", "calendar 2027", True), ("Feb 2027", "February 2027", True),
     ("end of 2028", "2028", True),
     # the quarter number is part of the period: Q1 and Q4 of one year are different horizons
     ("Q1 2027", "Q4 2027", False), ("Q1 2027", "q1 2027", True), ("Q2 2027", "Q3 2027", False),
     ("first quarter of 2027", "Q1 2027", True), ("fourth quarter 2027", "Q4 2027", True),
     ("4th quarter 2027", "Q4 2027", True), ("first quarter of 2027", "Q4 2027", False),
     ("Q1 2027", "Q1 2028", False), ("Q1 2027", "2027", False)],
)  # fmt: skip
def test_horizon_keys_normalise_wording_but_keep_period_basis(a, b, same):
    assert (ev.horizon_key(a) == ev.horizon_key(b)) is same


def test_a_forecast_assigned_to_the_wrong_quarter_is_not_credited_as_aligned():
    gold = [ev.GoldClaim("cpi_inflation", "Q1 2027", 0.5, "percent", None)]
    wrong = ev.extraction_counts([fc("cpi_inflation", "Q4 2027", 0.5)], gold)
    right = ev.extraction_counts([fc("cpi_inflation", "Q1 2027", 0.5)], gold)
    assert (wrong["aligned"], wrong["correct"], wrong["value_correct"]) == (0, 0, 0)
    assert (right["aligned"], right["correct"], right["value_correct"]) == (1, 1, 1)


def test_extraction_counts_alignment_scenario_and_values():
    gold = [ev.GoldClaim("gdp", "2027", 1.8, "percent", None),
            ev.GoldClaim("gdp", "2027", -0.5, "percent", "downside scenario"),
            ev.GoldClaim("ocr", "February 2027", 2.25, "percent", None)]  # fmt: skip
    predicted = [fc("gdp", "2027", 1.8), fc("gdp", "2027", -0.5),  # scenario missed
                 fc("cpi_inflation", "2027", 2.0)]  # fmt: skip
    counts = ev.extraction_counts(predicted, gold)
    assert counts == {"predicted": 3, "gold": 3, "aligned": 2, "correct": 1, "scenario_correct": 1,
                      "value_correct": 2}  # fmt: skip


def test_rates_handle_empty_denominators():
    assert ev.rate(0, 0) is None and ev.rate(1, 4) == 0.25


def test_completeness_counts_key_points_whose_words_all_appear():
    text = "Household spending is weak. China is the main risk."
    assert ev.completeness(text, [("household", "spending"), ("china",), ("tourism",)]) == (2, 3)


def test_indicator_scores_are_micro_averaged():
    assert ev.indicator_counts({"gdp", "ocr"}, {"gdp", "cpi_inflation"}) == (1, 2, 2)


def test_every_case_file_is_valid_and_synthetic():
    cases = ev.load_eval_set(EVAL_SET)
    assert len(cases) >= 10
    assert len({c.id for c in cases}) == len(cases)
    for case in cases:
        texts = [s.text for v in case.versions.values() for s in v.values()]
        assert any("SYNTHETIC FIXTURE" in t for t in texts), case.id
        assert any(c.role == "model" for c in case.candidates), case.id


@pytest.fixture(scope="module")
def report():
    return ev.run_eval(ev.load_eval_set(EVAL_SET), pricing={"test": Pricing(4.0, 20.0)})


def test_every_probe_behaves_as_labelled(report):
    misses = [p for p in report.probes if not p.as_expected]
    assert misses == [], [(p.case, p.candidate, sorted(p.errors)) for p in misses]


def test_difficult_cases_are_covered(report):
    covered = {code for p in report.probes for code in p.expected_errors}
    for code in ("historical_not_forecast", "period_basis_mismatch", "fiscal_calendar_mismatch",
                 "scenario_as_baseline", "superseded_value", "wrong_version", "instruction_like_evidence",
                 "quote_not_found", "page_outside_section", "missing_unit", "unit_mismatch",
                 "number_not_in_evidence", "direction_contradiction", "indicator_mismatch"):  # fmt: skip
        assert code in covered, code


def test_metrics_do_not_regress_below_the_recorded_baseline(report):
    m = report.metrics
    floors = ev.RECORDED_BASELINE
    for name, floor in floors.items():
        assert m[name] is not None and m[name] >= floor - 1e-9, (name, m[name], floor)


def test_markdown_report_names_the_limitations(report):
    md = report.to_markdown()
    assert "Replay" in md and "not a measurement of a real model" in md
    assert "| forecast precision (accepted)" in md


def test_clean_probes_are_never_rejected(report):
    assert report.metrics["probe_false_rejection_rate"] == 0.0


# --- relative horizons keep their wording -----------------------------------------------------
@pytest.mark.parametrize(
    ("a", "b", "same"),
    [("next year", "this year", False), ("next year", "Next  year.", True),
     ("next month", "next year", False), ("this quarter", "next quarter", False),
     ("medium term", "long term", False), ("next year", "2027", False)],
)  # fmt: skip
def test_relative_horizons_are_not_collapsed_to_one_empty_key(a, b, same):
    assert ev.horizon_key(a)  # never empty, so two different relative wordings cannot align
    assert (ev.horizon_key(a) == ev.horizon_key(b)) is same


def test_a_forecast_for_a_different_relative_period_is_not_credited():
    gold = [ev.GoldClaim("house_prices", "next year", 3.0, "percent", None)]
    wrong = ev.extraction_counts([fc("house_prices", "this year", 3.0)], gold)
    right = ev.extraction_counts([fc("house_prices", "next year", 3.0)], gold)
    assert (wrong["aligned"], wrong["correct"], wrong["value_correct"]) == (0, 0, 0)
    assert (right["aligned"], right["correct"], right["value_correct"]) == (1, 1, 1)


# --- a live evaluation spends only within the configured run budget -----------------------------
PRICE = Pricing(4.0, 20.0)


def live_cases():
    return ev.load_eval_set(EVAL_SET)


def test_a_live_evaluation_without_a_budget_is_refused_before_any_request():
    fake = FakeProvider("{}")
    with pytest.raises(ValueError, match="budget"):
        ev.run_eval(live_cases(), provider=fake)
    assert fake.calls == []


def test_a_budget_smaller_than_the_first_request_sends_nothing():
    fake = FakeProvider("{}")
    budget = ev.EvalBudget(PRICE, LlmLimits(max_run_usd=0.0001))
    with pytest.raises(ev.EvalBudgetExceeded):
        ev.run_eval(live_cases(), provider=fake, budget=budget)
    assert fake.calls == [] and budget.spent_usd == 0.0


def test_the_budget_stops_a_live_evaluation_before_the_request_that_would_exceed_it():
    fake = FakeProvider("{}", usage=(1_000, 200))
    budget = ev.EvalBudget(PRICE, LlmLimits(max_run_usd=0.1))
    with pytest.raises(ev.EvalBudgetExceeded):
        ev.run_eval(live_cases(), provider=fake, budget=budget)
    live = sum(len([c for c in case.candidates if c.role != "probe"]) for case in live_cases())
    assert 0 < len(fake.calls) < live
    assert budget.spent_usd == pytest.approx(len(fake.calls) * PRICE.cost(1_000, 200))
    assert budget.spent_usd <= budget.limits.max_run_usd


def test_a_sufficient_budget_runs_every_live_request_and_records_the_spend():
    fake = FakeProvider("{}", usage=(1_000, 200))
    budget = ev.EvalBudget(PRICE, LlmLimits(max_run_usd=5.0))
    report = ev.run_eval(live_cases(), provider=fake, budget=budget)
    assert len(fake.calls) == len(report.models) and report.mode == "live"
    assert budget.spent_usd == pytest.approx(len(fake.calls) * PRICE.cost(1_000, 200))
    assert all(
        p.as_expected for p in report.probes
    )  # probes are replayed, never sent to the provider

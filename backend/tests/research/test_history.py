"""Phase 3D-B forecast history: vintages, supersession, revisions and measure changes (SYNTHETIC FIXTURE claims)."""

from __future__ import annotations

import pytest

from nzstats.research.history import forecast_history

from .test_compare import claim

ANNUAL = "Annual CPI inflation"
AVERAGE = "CPI inflation, annual average"


def series_of(out, institution="alpha"):
    return [s for s in out.series if s.institution.key == institution]


def test_successive_publications_are_vintages_of_one_identity_oldest_first():
    out = forecast_history([
        claim(summary_id=3, published_on="2026-11-20", value=2.0),
        claim(summary_id=1, published_on="2026-05-20", value=2.6),
        claim(summary_id=2, published_on="2026-08-13", value=2.3),
    ])  # fmt: skip
    (s,) = out.series
    assert [v.published_on for v in s.vintages] == ["2026-05-20", "2026-08-13", "2026-11-20"]
    assert [v.value for v in s.vintages] == [2.6, 2.3, 2.0]
    assert [v.superseded for v in s.vintages] == [True, True, False]
    # Revisions are consecutive differences, computed by hand: 2.3 - 2.6 and 2.0 - 2.3.
    assert [v.revision for v in s.vintages] == [None, pytest.approx(-0.3), pytest.approx(-0.3)]
    assert s.n_revisions == 2 and s.total_revision == pytest.approx(-0.6)
    assert s.latest.summary_id == 3
    assert s.kind == "central" and s.horizon_key == "year_to:2027-06"


def test_an_unchanged_value_is_a_vintage_but_not_a_revision():
    out = forecast_history([
        claim(summary_id=1, published_on="2026-05-20", value=2.1),
        claim(summary_id=2, published_on="2026-08-13", value=2.1),
    ])  # fmt: skip
    (s,) = out.series
    assert len(s.vintages) == 2 and s.n_revisions == 0 and s.vintages[1].revision == 0


def test_a_change_of_measure_is_reported_and_never_treated_as_a_revision():
    out = forecast_history([
        claim(summary_id=1, published_on="2026-05-20", indicator_label=AVERAGE, value=2.9),
        claim(summary_id=2, published_on="2026-08-13", indicator_label=ANNUAL, value=2.1),
    ])  # fmt: skip
    assert len(out.series) == 2 and all(s.n_revisions == 0 for s in out.series)
    (change,) = out.measure_changes
    assert change.from_basis == "annual_average_change" and change.to_basis == "annual_change"
    assert change.from_summary_id == 1 and change.to_summary_id == 2
    assert "not a revision" in change.note


def test_a_document_that_adds_a_second_measure_is_not_a_measure_change():
    out = forecast_history([
        claim(summary_id=1, published_on="2026-05-20", indicator_label=ANNUAL, value=2.4),
        claim(summary_id=2, published_on="2026-08-13", indicator_label=ANNUAL, value=2.2),
        claim(summary_id=2, published_on="2026-08-13", indicator_label=AVERAGE, value=2.8),
    ])  # fmt: skip
    assert out.measure_changes == []
    annual = next(s for s in out.series if s.basis == "annual_change")
    assert annual.n_revisions == 1


def test_scenarios_are_separate_identities_from_the_central_forecast():
    out = forecast_history([
        claim(summary_id=1, published_on="2026-05-20", value=2.4),
        claim(summary_id=2, published_on="2026-08-13", value=3.5, scenario="High inflation"),
        claim(summary_id=3, published_on="2026-11-20", value=3.2, scenario="high  INFLATION"),
    ])  # fmt: skip
    central = [s for s in out.series if s.kind == "central"]
    scenario = [s for s in out.series if s.kind == "scenario"]
    assert len(central) == 1 and len(central[0].vintages) == 1
    assert len(scenario) == 1 and [v.value for v in scenario[0].vintages] == [3.5, 3.2]
    assert (
        out.measure_changes == []
    )  # a scenario is never a change of measure for the central forecast


def test_institutions_never_share_a_history():
    out = forecast_history([
        claim(institution="alpha", summary_id=1, published_on="2026-05-20", value=2.4),
        claim(institution="beta", summary_id=2, published_on="2026-08-13", value=2.0),
    ])  # fmt: skip
    assert len(out.series) == 2 and all(s.n_revisions == 0 for s in out.series)


def test_conflicts_and_ambiguous_claims_are_listed_not_used():
    out = forecast_history([
        claim(summary_id=1, published_on="2026-05-20", value=2.4),
        claim(summary_id=2, published_on="2026-08-13", value=2.1),
        claim(summary_id=2, published_on="2026-08-13", value=2.2),
        claim(summary_id=3, published_on="2026-09-01", horizon="next year", value=2.0),
    ])  # fmt: skip
    (s,) = out.series
    assert [v.value for v in s.vintages] == [2.4]
    reasons = [e.reason for e in out.excluded]
    assert sum("two different values" in r for r in reasons) == 2
    assert any("horizon" in r for r in reasons)


def test_original_values_and_evidence_are_kept_as_stated():
    evidence = [{"section_ordinal": 2, "page": 3, "quote": None}]
    out = forecast_history(
        [claim(summary_id=1, value=2.15, evidence=evidence, qualification="assumes stable oil")]
    )
    v = out.series[0].vintages[0]
    assert v.value == 2.15 and v.horizon == "year to June 2027" and v.indicator_label == ANNUAL
    assert v.qualification == "assumes stable oil" and v.evidence[0].page == 3


def test_a_vintage_without_a_publication_date_sorts_first_and_says_so():
    out = forecast_history([
        claim(summary_id=2, published_on="2026-08-13", value=2.1),
        claim(summary_id=1, published_on=None, value=2.5),
    ])  # fmt: skip
    (s,) = out.series
    assert [v.published_on for v in s.vintages] == [None, "2026-08-13"]


def test_output_is_independent_of_input_order():
    claims = [
        claim(summary_id=i, published_on=f"2026-0{i}-01", value=2.0 + i / 10, institution=inst)
        for i in range(1, 6) for inst in ("alpha", "beta")
    ]  # fmt: skip
    assert forecast_history(claims) == forecast_history(list(reversed(claims)))

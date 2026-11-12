"""Table figures against verified model claims (Phase 4AF). Agreement is recorded as agreement, never as proof."""

from dataclasses import fields
from decimal import Decimal

from nzstats.research.table_reconcile import Reconciliation, reconcile, summary_counts
from nzstats.research.table_store import StoredTableForecast

from .bank_support import nf

V = 7


def tab(
    i=1,
    *,
    value="2.6",
    horizon="year to June 2026",
    unit="percent",
    role="author",
    label="Annual CPI inflation (%)",
    indicator="cpi_inflation",
    kind="forecast",
    version=V,
    caption=None,
    missing=False,
):
    return StoredTableForecast(
        id=i, extraction_id=1, version_id=version, interpreter_version="tables-1", ordinal=i,
        indicator=indicator, label=label, period_text="Jun-26", horizon=horizon, kind=kind, unit=unit,
        raw_text=value if value else "", value=None if missing else Decimal(value), missing=missing,
        author_role=role, footnote=None, page=1, table=0, row=0, col=2,
        evidence={"caption": caption, "row_label": label},
    )  # fmt: skip


def claim(
    value=2.6,
    *,
    path="forecasts[0]",
    horizon="year to June 2026",
    unit="percent",
    label="Annual CPI inflation",
    version=V,
    **kw,
):
    return nf(
        summary_id=version,
        value=value,
        horizon=horizon,
        unit=unit,
        indicator_label=label,
        claim_path=path,
        **kw,
    )


def only(rs):
    (r,) = rs
    return r


def test_equal_figures_are_an_exact_match_even_if_printed_differently():
    r = only(reconcile([tab(value="2.60")], [claim(2.6)]))
    assert (r.cls, r.table_ids, r.claim_paths, r.version_id) == (
        "exact_match",
        (1,),
        ("forecasts[0]",),
        V,
    )


def test_a_figure_that_rounds_to_the_claim_is_a_rounding_difference_and_otherwise_a_contradiction():
    assert only(reconcile([tab(value="4.25")], [claim(4.3)])).cls == "rounding_difference"
    assert only(reconcile([tab(value="4.25")], [claim(4.2)])).cls == "contradictory_value"
    assert only(reconcile([tab(value="4.3")], [claim(4.25)])).cls == "rounding_difference"


def test_different_figures_contradict():
    assert only(reconcile([tab(value="2.6")], [claim(3.1)])).cls == "contradictory_value"


def test_the_same_number_in_different_units_is_a_units_mismatch_not_a_match():
    r = only(reconcile([tab(value="2.6")], [claim(2.6, unit="percentage_points")]))
    assert r.cls == "units_mismatch"


def test_a_lone_pair_with_different_horizons_is_a_horizon_mismatch():
    r = only(
        reconcile(
            [tab(horizon="year to June 2026")], [claim(2.6, horizon="year to September 2026")]
        )
    )
    assert (r.cls, r.table_ids, r.claim_paths) == ("horizon_mismatch", (1,), ("forecasts[0]",))


def test_several_unmatched_horizons_are_just_without_counterpart():
    tables = [tab(1, horizon="year to June 2026"), tab(2, horizon="year to September 2026")]
    claims = [
        claim(2.6, path="forecasts[0]", horizon="year to December 2026"),
        claim(2.2, path="forecasts[1]", horizon="year to March 2027"),
    ]
    assert {r.cls for r in reconcile(tables, claims)} == {"no_counterpart"}


def test_a_figure_the_table_attributes_to_someone_else_is_an_attribution_mismatch():
    assert only(reconcile([tab(role="third_party")], [claim(2.6)])).cls == "attribution_mismatch"


def test_unpaired_items_have_no_counterpart_in_either_direction():
    rs = reconcile(
        [
            tab(1),
            tab(2, indicator="ocr", label="OCR (%)", horizon="June 2026 quarter", value="3.25"),
        ],
        [
            claim(2.6),
            claim(
                5.0,
                path="forecasts[1]",
                indicator="unemployment",
                label="Unemployment rate",
                horizon="June 2026 quarter",
            ),
        ],
    )
    assert summary_counts(rs) == {"exact_match": 1, "no_counterpart": 2}


def test_two_claims_that_disagree_make_the_match_ambiguous():
    rs = reconcile([tab()], [claim(2.6, path="forecasts[0]"), claim(3.1, path="forecasts[1]")])
    assert summary_counts(rs) == {"ambiguous_or_unsupported": 1}
    assert set(rs[0].claim_paths) == {"forecasts[0]", "forecasts[1]"}


def test_identical_repeats_are_one_statement():
    rs = reconcile([tab()], [claim(2.6, path="forecasts[0]"), claim(2.6, path="forecasts[3]")])
    assert [(r.cls, set(r.claim_paths)) for r in rs] == [
        ("exact_match", {"forecasts[0]", "forecasts[3]"})
    ]


def test_a_claim_whose_measure_cannot_be_read_is_unsupported():
    rs = reconcile([tab()], [claim(2.6, label="Core CPI inflation")])
    assert summary_counts(rs) == {"ambiguous_or_unsupported": 1, "no_counterpart": 1}


def test_adjustment_and_document_keep_figures_apart():
    adj = reconcile([tab(label="Annual CPI inflation (%), seasonally adjusted")], [claim(2.6)])
    assert summary_counts(adj) == {"no_counterpart": 2}
    other = reconcile([tab(version=8)], [claim(2.6, version=V)])
    assert summary_counts(other) == {"no_counterpart": 2}


def test_adjustment_in_table_note_is_used_in_reconciliation():
    from dataclasses import replace

    t = tab()
    t = replace(t, evidence={**t.evidence, "notes": ["Note: seasonally adjusted"]})
    assert only(reconcile([t], [claim(2.6, adjustment="seasonally_adjusted")])).cls == "exact_match"


def test_adjustment_in_column_header_is_used_in_reconciliation():
    from dataclasses import replace

    t = tab()
    t = replace(t, evidence={**t.evidence, "header_texts": ["Forecast (seasonally adjusted)"]})
    assert only(reconcile([t], [claim(2.6, adjustment="seasonally_adjusted")])).cls == "exact_match"


def test_conflicting_adjustment_in_note_is_not_reconciled_as_unstated():
    from dataclasses import replace

    t = tab(label="Annual CPI inflation, unadjusted (%)")
    t = replace(t, evidence={**t.evidence, "notes": ["Note: seasonally adjusted"]})
    assert only(reconcile([t], [])).cls == "ambiguous_or_unsupported"


def test_actuals_and_missing_figures_are_not_forecasts_to_reconcile():
    rs = reconcile([tab(kind="actual"), tab(2, missing=True, value=None)], [])
    assert rs == []


def test_there_is_no_verified_flag_on_a_reconciliation():
    assert "verified" not in {f.name for f in fields(Reconciliation)}
    assert {f.name for f in fields(Reconciliation)} == {
        "version_id",
        "table_ids",
        "claim_paths",
        "cls",
        "note_code",
    }


def test_a_scenario_claim_is_not_the_central_forecast_and_is_not_reconciled_with_it():
    rs = reconcile([tab(value="3.00")], [claim(3.0, scenario="downside")])
    assert summary_counts(rs) == {
        "no_counterpart": 1
    }  # only the table figure; the scenario claim is left alone

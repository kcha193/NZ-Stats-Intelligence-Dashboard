"""SYNTHETIC PDFs: semantic context must survive every boundary, without a model reading."""

import pytest

from nzstats.research.bank_analytics import bank_comparison
from nzstats.research.bank_view import BankView
from nzstats.research.compare import basis_of
from nzstats.research.table_reconcile import reconcile
from nzstats.research.table_store import load_forecasts, load_rejections
from nzstats.sources.artifacts import ArtifactStore

from .pdf_table_support import table_pdf
from .test_table_reconcile import claim, tab
from .test_table_view import run, stored


@pytest.fixture()
def artifacts(tmp_path):
    return ArtifactStore(tmp_path / "raw")


def document(context="", location="caption", *, label="Annual CPI inflation (%)", value="2.6"):
    items = [(400, 714, "Forecast"), (400, 700, "Dec-26"), (72, 686, label), (400, 686, value)]
    if location == "caption":
        items.append((72, 745, f"Table 1: {context} forecasts (%)"))
    elif location == "heading":
        items.append((72, 745, context))
    elif location == "note":
        items.append((72, 665, f"Note: {context}"))
    elif location == "group":
        items[0] = (400, 714, f"Forecast ({context})")
    elif location == "column":
        items[1] = (400, 700, f"Dec-26 {context}")
    elif location == "row":
        items[2] = (72, 686, f"{context} {label}")
    else:
        raise AssertionError(location)
    return items


@pytest.mark.parametrize("location", ["caption", "note", "group", "row"])
@pytest.mark.parametrize(
    "context",
    ["Annual average", "Australia", "Youth", "Downside scenario", "Provisional estimates"],
)
def test_unsupported_context_never_reaches_analytics(conn, artifacts, location, context):
    registry, version = stored(conn, artifacts, table_pdf([document(context, location)]))
    forecasts, _, _ = run(conn, registry)
    assert forecasts == []
    assert load_forecasts(conn, version) == []
    assert load_rejections(conn, version)
    view = BankView(forecasts, [], [], list(registry.values()), [])
    assert all(not comparison.groups for _, comparison in bank_comparison(view))


@pytest.mark.parametrize("location", ["caption", "note", "group", "row"])
def test_third_party_context_is_not_publisher_attributed(conn, artifacts, location):
    registry, version = stored(conn, artifacts, table_pdf([document("RBNZ", location)]))
    figures = load_forecasts(conn, version)
    assert figures and {f.author_role for f in figures} == {"third_party"}
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize("location", ["caption", "note", "group", "row"])
def test_cadence_conflict_is_refused_at_every_location(conn, artifacts, location):
    body = table_pdf([document("Annual % change", location, label="Quarterly real GDP growth (%)")])
    registry, version = stored(conn, artifacts, body)
    assert run(conn, registry)[0] == []
    assert load_forecasts(conn, version) == []
    assert {r.code for r in load_rejections(conn, version)} == {"contradictory_period"}


@pytest.mark.parametrize("location", ["caption", "note", "group", "row"])
def test_adjustment_has_identical_normalization_and_reconciliation(conn, artifacts, location):
    registry, version = stored(
        conn, artifacts, table_pdf([document("seasonally adjusted", location)])
    )
    forecasts, _, _ = run(conn, registry)
    assert len(forecasts) == 1 and forecasts[0].adjustment == "seasonally_adjusted"
    f = forecasts[0]
    rs = reconcile(load_forecasts(conn, version), [f])
    assert [r.cls for r in rs] == ["exact_match"]


@pytest.mark.parametrize(
    "context",
    ["Annual average", "Australia", "Youth", "Downside scenario", "Provisional estimates"],
)
@pytest.mark.parametrize("with_claim", [False, True])
def test_reconciliation_rejects_unsupported_evidence_without_counterpart_dependency(
    context, with_claim
):
    t = tab(caption=f"Table 1: {context} forecasts (%)")
    rs = reconcile([t], [claim()] if with_claim else [])
    assert [r.cls for r in rs if r.table_ids] == ["ambiguous_or_unsupported"]


def test_note_unit_and_value_unit_cannot_be_discarded(conn, artifacts):
    for items in [
        document("All figures in basis points", "note"),
        document("", "note", label="OCR (basis points)", value="25%"),
    ]:
        registry, version = stored(conn, artifacts, table_pdf([items]))
        assert load_forecasts(conn, version) == []
        assert {r.code for r in load_rejections(conn, version)} == {"contradictory_unit"}
        assert run(conn, registry)[0] == []


def test_year_to_caption_cannot_become_a_quarter(conn, artifacts):
    registry, version = stored(
        conn,
        artifacts,
        table_pdf([document("Year to December", label="Quarterly real GDP growth (%)")]),
    )
    assert load_forecasts(conn, version) == []
    assert {r.code for r in load_rejections(conn, version)} == {"contradictory_period"}
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize(
    "context", ["Australian forecasts (%)", "Annual average forecasts (%)", "Youth forecasts (%)"]
)
def test_unnumbered_context_heading_is_preserved(conn, artifacts, context):
    registry, version = stored(conn, artifacts, table_pdf([document(context, "heading")]))
    assert load_forecasts(conn, version) == []
    assert load_rejections(conn, version)
    assert run(conn, registry)[0] == []


def test_qualified_continuation_cannot_discard_new_scope(conn, artifacts):
    first = document("Central")
    second = document("Australia", "caption")
    second[-1] = (72, 745, "Table 1 (continued): Australia")
    registry, version = stored(conn, artifacts, table_pdf([first, second]))
    assert {f.page for f in load_forecasts(conn, version)} == {1}
    assert run(conn, registry)[0]
    assert load_rejections(conn, version)


def test_unit_cell_evidence_survives_storage(conn, artifacts):
    items = [
        (210, 700, "Unit"),
        (300, 714, "Forecast"),
        (300, 700, "Dec-26"),
        (72, 686, "Annual CPI inflation"),
        (210, 686, "% y/y"),
        (300, 686, "2.6"),
    ]
    _, version = stored(conn, artifacts, table_pdf([items]))
    (figure,) = load_forecasts(conn, version)
    assert figure.evidence["unit_texts"] == ["% y/y"]


def test_conflicting_adjustments_are_not_an_unstated_partition(conn, artifacts):
    items = document("seasonally adjusted", "note", label="Annual CPI inflation, unadjusted (%)")
    registry, version = stored(conn, artifacts, table_pdf([items]))
    assert load_forecasts(conn, version) == []
    assert {r.code for r in load_rejections(conn, version)} == {"contradictory_adjustment"}
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize("context", ["Canadian", "Adults", "Median", "Working age", "Nominal"])
@pytest.mark.parametrize("location", ["caption", "note", "group"])
def test_unrepresented_context_is_refused_instead_of_discarded(conn, artifacts, context, location):
    registry, version = stored(conn, artifacts, table_pdf([document(context, location)]))
    assert load_forecasts(conn, version) == []
    assert load_rejections(conn, version)
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize(
    "context",
    ["Australian forecasts", "Annual average forecasts", "Youth forecasts", "Downside scenario"],
)
def test_document_title_scope_is_not_discarded(conn, artifacts, context):
    registry, version = stored(conn, artifacts, table_pdf([document("Central")]), title=context)
    assert load_forecasts(conn, version) == []
    assert load_rejections(conn, version)
    assert run(conn, registry)[0] == []


def test_two_caption_lines_preserve_earlier_scope(conn, artifacts):
    items = document("Central") + [(72, 770, "Youth unemployment")]
    registry, version = stored(conn, artifacts, table_pdf([items]))
    assert load_forecasts(conn, version) == []
    assert load_rejections(conn, version)
    assert run(conn, registry)[0] == []


def test_mismatched_numbered_continuation_cannot_inherit_context(conn, artifacts):
    first = document("RBNZ")
    second = document("Central")
    second[-1] = (72, 745, "Table 2 (continued)")
    registry, version = stored(conn, artifacts, table_pdf([first, second]))
    assert {f.page for f in load_forecasts(conn, version)} == {1}
    assert load_rejections(conn, version)
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize("context", ["calendar year", "quarter end", "quarter ended December"])
@pytest.mark.parametrize("location", ["caption", "note", "group"])
def test_explicit_period_context_cannot_become_year_to(conn, artifacts, context, location):
    registry, version = stored(conn, artifacts, table_pdf([document(context, location)]))
    assert load_forecasts(conn, version) == []
    assert load_rejections(conn, version)
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize("location", ["caption", "note", "row"])
def test_explicit_actual_context_cannot_inherit_forecast_classification(conn, artifacts, location):
    registry, version = stored(conn, artifacts, table_pdf([document("Actuals", location)]))
    assert not any(f.kind == "forecast" for f in load_forecasts(conn, version))
    assert load_rejections(conn, version)
    assert run(conn, registry)[0] == []


def test_document_title_attribution_and_adjustment_are_retained(conn, artifacts):
    registry, version = stored(
        conn, artifacts, table_pdf([document("Central")]), title="RBNZ forecasts"
    )
    assert {f.author_role for f in load_forecasts(conn, version)} == {"third_party"}
    assert run(conn, registry)[0] == []

    registry, version = stored(
        conn,
        artifacts,
        table_pdf([document("Central", value="2.7")]),
        title="Seasonally adjusted forecasts",
    )
    forecasts, _, _ = run(conn, registry)
    assert forecasts and {f.adjustment for f in forecasts} == {"seasonally_adjusted"}
    assert [r.cls for r in reconcile(load_forecasts(conn, version), forecasts)] == ["exact_match"]


@pytest.mark.parametrize("context", ["Annual average", "Youth", "Australia", "RBNZ"])
def test_left_header_context_is_never_dropped(conn, artifacts, context):
    items = document("Central") + [(72, 714, context)]
    registry, version = stored(conn, artifacts, table_pdf([items]))
    assert run(conn, registry)[0] == []
    if context == "RBNZ":
        assert {f.author_role for f in load_forecasts(conn, version)} == {"third_party"}
    else:
        assert load_rejections(conn, version)


@pytest.mark.parametrize(
    "context",
    ["Annual average", "Youth", "Australia", "Provisional estimates", "Downside scenario"],
)
def test_wrapped_note_qualification_is_not_dropped(conn, artifacts, context):
    items = document("Central") + [(72, 665, "Note: All figures are"), (72, 651, context)]
    registry, version = stored(conn, artifacts, table_pdf([items]))
    assert load_forecasts(conn, version) == []
    assert load_rejections(conn, version)
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize("location", ["caption", "note", "group", "row"])
@pytest.mark.parametrize(
    "context", ["ANZ", "ASB", "BNZ", "Westpac", "Kiwibank", "Example Research and RBNZ"]
)
def test_peer_or_mixed_forecaster_cannot_be_publisher_attributed(
    conn, artifacts, context, location
):
    registry, version = stored(conn, artifacts, table_pdf([document(context, location)]))
    figures = load_forecasts(conn, version)
    assert figures and {f.author_role for f in figures} == {"third_party"}
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize("context", ["Canadian", "Adults", "Median", "Nominal"])
def test_unrepresented_document_title_is_refused(conn, artifacts, context):
    registry, version = stored(
        conn, artifacts, table_pdf([document("Central")]), title=f"{context} forecasts"
    )
    assert load_forecasts(conn, version) == []
    assert load_rejections(conn, version)
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize(
    "context", ["All figures are percentage changes", "All figures are growth"]
)
@pytest.mark.parametrize("label", ["Unemployment rate (%)", "OCR (%)"])
def test_change_in_a_rate_is_never_a_rate_level(conn, artifacts, context, label):
    registry, version = stored(conn, artifacts, table_pdf([document(context, "note", label=label)]))
    assert {r.code for r in load_rejections(conn, version)} == {"unsupported_measure"}
    assert load_forecasts(conn, version) == []
    assert load_rejections(conn, version)
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize(
    "label",
    [
        "Average annual CPI inflation (%)",
        "Annual CPI inflation average (%)",
    ],
)
def test_average_wording_cannot_fall_back_to_annual_change(conn, artifacts, label):
    registry, version = stored(conn, artifacts, table_pdf([document("Central", label=label)]))
    assert load_forecasts(conn, version) == []
    assert load_rejections(conn, version)
    assert run(conn, registry)[0] == []


def test_wrapped_marker_note_does_not_qualify_unmarked_cells(conn, artifacts):
    items = document("Central") + [
        (72, 665, "* Marked figures are"),
        (72, 651, "seasonally adjusted"),
    ]
    registry, version = stored(conn, artifacts, table_pdf([items]))
    forecasts, _, _ = run(conn, registry)
    assert forecasts and {f.adjustment for f in forecasts} == {"not_stated"}
    assert load_forecasts(conn, version)[0].evidence["notes"] == [
        "* Marked figures are seasonally adjusted"
    ]


def _basis(n):
    f = n.forecast
    return basis_of(f.indicator, f.indicator_label, f.horizon, f.unit)


@pytest.mark.parametrize("context", ["Central", "Annual average"])
@pytest.mark.parametrize(
    "label", ["Annual average CPI inflation (%)", "Annual-average CPI inflation (%)"]
)
def test_a_label_stating_annual_average_keeps_that_basis_in_both_paths(
    conn, artifacts, context, label
):
    registry, version = stored(conn, artifacts, table_pdf([document(context, label=label)]))
    forecasts, _, _ = run(conn, registry)
    assert [_basis(n) for n in forecasts] == ["annual_average_change"]
    stored_rows = load_forecasts(conn, version)
    horizon = "year to December 2026"
    same = claim(label="Annual average CPI inflation", horizon=horizon, version=version)
    through_year = claim(label="Annual CPI inflation", horizon=horizon, version=version)
    assert [r.cls for r in reconcile(stored_rows, [same]) if r.table_ids] == ["exact_match"]
    # An annual-average figure never stands in for the through-the-year rate.
    assert [r.cls for r in reconcile(stored_rows, [through_year]) if r.table_ids] != ["exact_match"]


@pytest.mark.parametrize(
    ("context", "location", "label"),
    [
        ("Annual % change", "caption", "Annual average CPI inflation (%)"),
        ("y/y", "group", "Annual average CPI inflation (%)"),
        ("Annual average", "caption", "Annual % change in CPI (%)"),
        ("Annual average", "note", "CPI inflation, y/y (%)"),
    ],
)
def test_annual_average_and_through_year_in_one_reading_are_contradictory(
    conn, artifacts, context, location, label
):
    registry, version = stored(
        conn, artifacts, table_pdf([document(context, location, label=label)])
    )
    assert load_forecasts(conn, version) == []
    assert {r.code for r in load_rejections(conn, version)} == {"contradictory_period"}
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize(
    "title",
    [
        "Quarterly Economic Overview",
        "Quarterly Economic Outlook November 2026",
        "Economic Update",
    ],
)
def test_a_publication_name_does_not_qualify_the_tables_inside_it(conn, artifacts, title):
    registry, version = stored(conn, artifacts, table_pdf([document("Central")]), title=title)
    forecasts, _, _ = run(conn, registry)
    assert [_basis(n) for n in forecasts] == ["annual_change"]


@pytest.mark.parametrize("title", ["Quarterly forecasts", "Annual average forecasts"])
def test_a_title_stating_a_measure_still_qualifies_it(conn, artifacts, title):
    registry, version = stored(conn, artifacts, table_pdf([document("Central")]), title=title)
    assert load_forecasts(conn, version) == []
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize("context", ["Key", "Main", "Summary of", "Selected"])
def test_neutral_caption_words_do_not_refuse_the_table(conn, artifacts, context):
    registry, version = stored(conn, artifacts, table_pdf([document(context)]))
    assert [_basis(n) for n in run(conn, registry)[0]] == ["annual_change"]


@pytest.mark.parametrize("header", ["Mar-27 yr", "Dec-26"])
def test_documented_period_headers_are_not_unknown_context(conn, artifacts, header):
    items = document("Central")
    items[1] = (400, 700, header)
    registry, version = stored(conn, artifacts, table_pdf([items]))
    assert load_rejections(conn, version) == []
    assert [_basis(n) for n in run(conn, registry)[0]] == ["annual_change"]

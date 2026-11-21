"""The owner-reviewed canonical series mapping (Phase 4AR, interpreter `xlsx-anz-4`; design in Phase 4AQ §3).

Fictional workbooks only: a headline real-GDP block beside a variant, a headline CPI block beside a variant, and an
unemployment column whose unit is stated only in a note. Every figure, title and note is invented.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from nzstats.research.table_context import stored_context_rejection
from nzstats.research.table_ingest import candidate_hash8
from nzstats.research.xlsx_anz import (
    INTERPRETER_VERSION,
    MAPPED_INTERPRETER_VERSION,
    interpret_anz_workbook,
    mapping_from_positions,
    mapping_refusal,
)
from nzstats.research.xlsx_cells import read_cells
from nzstats.research.xlsx_mapping import MappingRefused, parse_mapping

from .test_xlsx_anz import (
    AS_AT,
    CPI_AA,
    GDP_AA,
    GDP_QQ,
    LEGEND,
    PUBLISHER,
    SHA,
    TITLE,
    UNEMP,
    data_sheet,
    run,
    series,
    standard,
)
from .xlsx_support import Sheet, build

GROWTH = (
    "Growth Tracker"  # "tracker" is outside the neutral context words: the sheet name needs review
)
PRICES = "Prices"
UNIT_NOTE = "Unemployment rate in percent"
UNIT_CELL = (
    "A15"  # notes start two rows below the eight dates: A13 legend, A14 "as at", A15 this note
)
GDP_VARIANT = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]
CPI_VARIANT = [3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8]


def headline_gdp(*, header="% q/q", values=GDP_QQ, **kw):
    return ("Real GDP", [(header, series(values, **kw)), ("Annual % change", series(GDP_AA))])


def sheets(
    *,
    growth=None,
    prices=None,
    prices_notes=(LEGEND, AS_AT, UNIT_NOTE),
    growth_notes=(LEGEND, AS_AT),
):
    growth = growth or [headline_gdp(), ("Real GDP production", [("% q/q", series(GDP_VARIANT))])]
    prices = prices or [
        ("CPI inflation", [("Annual % change", series(CPI_AA))]),
        ("CPI non-tradables inflation", [("Annual % change", series(CPI_VARIANT))]),
        ("Unemployment rate", [(None, series(UNEMP))]),
    ]
    return [
        Sheet("Cover"),
        data_sheet(GROWTH, growth, notes=growth_notes),
        data_sheet(PRICES, prices, notes=prices_notes),
    ]


def gdp_entry(**kw):
    return {"indicator": "gdp", "basis": "quarterly", "sheet": 2, "sheet_name": GROWTH, "block": 1,
            "block_title": "Real GDP", "column": "B", "unit_header": "% q/q", "unit_evidence": None, **kw}  # fmt: skip


def cpi_entry(**kw):
    return {"indicator": "cpi_inflation", "basis": "annual", "sheet": 3, "sheet_name": PRICES, "block": 1,
            "block_title": "CPI inflation", "column": "B", "unit_header": "Annual % change", "unit_evidence": None,
            **kw}  # fmt: skip


def unemployment_entry(**kw):
    return {"indicator": "unemployment", "basis": "quarterly", "sheet": 3, "sheet_name": PRICES, "block": 3,
            "block_title": "Unemployment rate", "column": "D", "unit_header": "",
            "unit_evidence": {"sheet": 3, "cell": UNIT_CELL, "text": UNIT_NOTE}, **kw}  # fmt: skip


def manifest(*, series=None, sheet_context=None, **kw) -> dict:
    return {
        "schema": "anz-workbook-mapping-1",
        "workbook_sha256": SHA,
        "reviewer": "owner",
        "decided_on": "2026-11-22",
        "published_on": "not_stated",
        "series": [gdp_entry(), cpi_entry(), unemployment_entry()] if series is None else series,
        "sheet_context": (
            [{"sheet": 2, "sheet_name": GROWTH, "classification": "editorial"}]
            if sheet_context is None
            else sheet_context
        ),
        **kw,
    }


def body(doc: dict) -> bytes:
    return json.dumps(doc).encode()


def workbook(sheet_list):
    return read_cells(build(sheet_list, drawing_paragraphs=(("Fictional Bank",),)), isolate=False)


def mapped(sheet_list=None, doc=None):
    m = parse_mapping(body(manifest() if doc is None else doc))
    return interpret_anz_workbook(
        workbook(sheets() if sheet_list is None else sheet_list),
        publisher_names=PUBLISHER, document_title=TITLE, workbook_sha256=SHA, mapping=m,
    )  # fmt: skip


def at(rejections, code):
    return sorted((r.page, r.table, r.col) for r in rejections if r.code == code)


def by(forecasts, indicator):
    return [f for f in forecasts if f.indicator == indicator]


# --- without a manifest: exactly xlsx-anz-3 ------------------------------------------------------------------------


def test_the_versions_are_pinned():
    assert (INTERPRETER_VERSION, MAPPED_INTERPRETER_VERSION) == ("xlsx-anz-3", "xlsx-anz-4")


def test_without_a_manifest_the_results_equal_the_pre_4ar_goldens():
    # Codes recorded from main 880742b before any Phase 4AR change.
    forecasts, rejections = run(standard())
    assert (len(forecasts), rejections, candidate_hash8(forecasts)) == (12, (), "fdc24865")
    two = standard(growth=[("Real GDP", [("% q/q", series(GDP_QQ))]), ("Real GDP production", [("% q/q", series(GDP_AA))])])  # fmt: skip
    forecasts, rejections = run(two)
    assert (len(forecasts), sorted(codes := [r.code for r in rejections]), candidate_hash8(forecasts)) == (
        6, ["ambiguous_indicator"] * 2, "439ccf98",
    )  # fmt: skip
    assert codes


def test_an_explicit_none_mapping_is_the_unmapped_path():
    wb = workbook(sheets())
    kw = {"publisher_names": PUBLISHER, "document_title": TITLE, "workbook_sha256": SHA}
    assert interpret_anz_workbook(wb, **kw) == interpret_anz_workbook(wb, mapping=None, **kw)
    _, rejections = interpret_anz_workbook(wb, **kw)
    assert {r.code for r in rejections} >= {"ambiguous_indicator", "unit_unstated"}


# --- selection --------------------------------------------------------------------------------------------------------


def test_the_approved_canonical_columns_give_candidates_with_provenance():
    forecasts, rejections = mapped()
    gdp, cpi, unemployment = (
        by(forecasts, "gdp"),
        by(forecasts, "cpi_inflation"),
        by(forecasts, "unemployment"),
    )
    assert {(f.page, f.col) for f in gdp} == {(2, 2)}
    assert {(f.page, f.col) for f in cpi} == {(3, 2)}
    assert {(f.page, f.col) for f in unemployment} == {(3, 4)}
    assert len(gdp) == len(cpi) == len(unemployment) == 3
    assert {f.unit for f in forecasts} == {"percent"}
    assert {f.author_role for f in forecasts} == {"author"}
    m = parse_mapping(body(manifest()))
    first = gdp[0].evidence
    assert first["mapping_sha256"] == m.sha256
    assert (first["mapping_reviewer"], first["mapping_decided_on"]) == ("owner", "2026-11-22")
    assert first["mapping_entry"] == gdp_entry()
    assert first["caption"] == GROWTH  # the original name is kept
    assert first["caption_review"] == {
        "classification": "editorial", "sheet_name": GROWTH, "mapping_sha256": m.sha256, "decided_on": "2026-11-22",
    }  # fmt: skip
    assert unemployment[0].evidence["unit_evidence"] == {
        "sheet": 3,
        "cell": UNIT_CELL,
        "text": UNIT_NOTE,
    }
    assert "caption_review" not in cpi[0].evidence  # "Prices" was not reviewed and needs no review


def test_variant_and_unlisted_columns_naming_a_mapped_indicator_are_not_canonical():
    _, rejections = mapped()
    # Growth C (the headline block's unlisted annual column), Growth D (variant) and Prices C (CPI variant).
    assert at(rejections, "not_canonical_series") == [(2, 1, 3), (2, 2, 4), (3, 2, 3)]
    assert at(rejections, "ambiguous_indicator") == []


def test_the_manifest_not_the_position_chooses_between_two_plausible_headlines():
    doc = manifest(series=[gdp_entry(block=2, block_title="Real GDP production", column="D")])
    forecasts, rejections = mapped(doc=doc)
    assert {(f.page, f.col) for f in by(forecasts, "gdp")} == {(2, 4)}
    assert at(rejections, "not_canonical_series")[:2] == [(2, 1, 2), (2, 1, 3)]
    # CPI is not in this manifest: its two blocks keep the xlsx-anz-3 refusal.
    assert at(rejections, "ambiguous_indicator") == [(3, 1, 2), (3, 2, 3)]


def test_a_second_basis_from_the_same_headline_block_is_allowed():
    annual = gdp_entry(basis="annual", column="C", unit_header="Annual % change")
    forecasts, _ = mapped(doc=manifest(series=[gdp_entry(), annual]))
    gdp = by(forecasts, "gdp")
    assert {f.col for f in gdp} == {2, 3}
    assert len({f.horizon for f in gdp if f.col == 2} & {f.horizon for f in gdp if f.col == 3}) == 0


def test_no_indicator_and_horizon_is_contributed_twice():
    annual = gdp_entry(basis="annual", column="C", unit_header="Annual % change")
    forecasts, _ = mapped(
        doc=manifest(series=[gdp_entry(), annual, cpi_entry(), unemployment_entry()])
    )
    pairs = Counter((f.indicator, f.horizon) for f in forecasts)
    assert pairs and max(pairs.values()) == 1


# --- whole-manifest refusals ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "series_list",
    [
        [
            gdp_entry(),
            gdp_entry(column="D", block=2, block_title="Real GDP production"),
        ],  # one (indicator, basis) twice
        [gdp_entry(), cpi_entry(sheet=2, sheet_name=GROWTH, column="B")],  # one column twice
        # one indicator from two different blocks, even with different bases
        [
            gdp_entry(),
            gdp_entry(basis="annual", block=2, block_title="Real GDP production", column="D"),
        ],
    ],
)
def test_duplicate_canonical_mappings_refuse_the_whole_manifest(series_list):
    with pytest.raises(MappingRefused) as caught:
        parse_mapping(body(manifest(series=series_list)))
    assert caught.value.code == "mapping_duplicate"


def test_a_sheet_reviewed_twice_is_a_duplicate():
    twice = [
        {"sheet": 2, "sheet_name": GROWTH, "classification": c}
        for c in ("editorial", "substantive")
    ]
    with pytest.raises(MappingRefused) as caught:
        parse_mapping(body(manifest(sheet_context=twice)))
    assert caught.value.code == "mapping_duplicate"


@pytest.mark.parametrize(
    "doc",
    [
        manifest(series=[gdp_entry(indicator="ocr")]),
        manifest(series=[gdp_entry(basis="monthly")]),
        manifest(series=[gdp_entry(unit_evidence={"sheet": 2, "cell": "A15", "text": UNIT_NOTE})]),
        manifest(
            series=[
                unemployment_entry(unit_evidence={"sheet": 2, "cell": UNIT_CELL, "text": UNIT_NOTE})
            ]
        ),
        manifest(
            series=[
                unemployment_entry(unit_evidence={"sheet": 3, "cell": "15A", "text": UNIT_NOTE})
            ]
        ),
        manifest(series=[]),
        manifest(schema="anz-workbook-mapping-0"),
        manifest(reviewer="agent"),
        manifest(decided_on="22/11/2026"),
        manifest(workbook_sha256="C" * 64),
        manifest(series=[gdp_entry(sheet=True)]),
        manifest(series=[gdp_entry(column="b")]),
        manifest(series=[gdp_entry(extra="x")]),
        manifest(sheet_context=[{"sheet": 2, "sheet_name": GROWTH, "classification": "fine"}]),
        manifest(published_on={"date": "2026-11-05", "sheet": 2, "cell": "A14"}),
        manifest(published_on="2026-11-05"),
        {**manifest(), "unknown": 1},
        {k: v for k, v in manifest().items() if k != "sheet_context"},
    ],
)
def test_an_invalid_manifest_is_refused_whole(doc):
    with pytest.raises(MappingRefused) as caught:
        parse_mapping(body(doc))
    assert caught.value.code == "mapping_invalid"


@pytest.mark.parametrize(
    "raw", [b"", b"{", b"[]", b"\xff", b'{"a": 1, "a": 2}', b" " * (256 * 1024 + 1)]
)
def test_unreadable_or_oversized_manifest_bytes_are_invalid(raw):
    with pytest.raises(MappingRefused) as caught:
        parse_mapping(raw)
    assert caught.value.code == "mapping_invalid"


def test_the_mapping_hash_is_the_hash_of_the_exact_bytes():
    import hashlib

    raw = body(manifest())
    assert parse_mapping(raw).sha256 == hashlib.sha256(raw).hexdigest()
    assert parse_mapping(raw + b"\n").sha256 != parse_mapping(raw).sha256


def test_a_wrong_workbook_hash_refuses_the_manifest():
    m = parse_mapping(body(manifest(workbook_sha256="d" * 64)))
    assert mapping_refusal(m, workbook(sheets()), SHA) == "mapping_hash_mismatch"
    assert mapping_refusal(parse_mapping(body(manifest())), workbook(sheets()), SHA) is None


def test_the_stated_publication_cell_must_hold_the_recorded_text():
    good = {"date": "2026-11-05", "sheet": 3, "cell": "A14", "text": AS_AT}
    wb = workbook(sheets())
    assert mapping_refusal(parse_mapping(body(manifest(published_on=good))), wb, SHA) is None
    for wrong in (
        {**good, "text": "Data as at 6 November 2026"},
        {**good, "cell": "A13"},
        {**good, "sheet": 9},
    ):
        m = parse_mapping(body(manifest(published_on=wrong)))
        assert mapping_refusal(m, wb, SHA) == "mapping_structure_mismatch"


# --- structure changes ------------------------------------------------------------------------------------------------


def _gdp_refused(rejections, code="mapping_structure_mismatch"):
    return [x for x in at(rejections, code) if x[0] in (2, 3)]


def test_a_moved_worksheet_is_a_structure_mismatch():
    s = sheets()
    forecasts, rejections = mapped([s[0], s[2], s[1]])
    assert (
        by(forecasts, "gdp")
        == by(forecasts, "cpi_inflation")
        == by(forecasts, "unemployment")
        == []
    )
    assert len(at(rejections, "mapping_structure_mismatch")) == 3


def test_a_moved_column_is_a_structure_mismatch():
    inserted = [("Real GDP per capita", [("% q/q", series(GDP_VARIANT))]), headline_gdp()]
    forecasts, rejections = mapped(sheets(growth=inserted))
    assert by(forecasts, "gdp") == []
    assert (2, 1, 2) in at(rejections, "mapping_structure_mismatch")
    assert (2, 2, 3) in at(
        rejections, "not_canonical_series"
    )  # the headline, now unlisted at C, is not taken


def test_a_modified_block_title_is_a_structure_mismatch():
    growth = [("Real GDP (revised)", headline_gdp()[1])]
    forecasts, rejections = mapped(sheets(growth=growth))
    assert by(forecasts, "gdp") == []
    assert (2, 1, 2) in at(rejections, "mapping_structure_mismatch")


def test_a_modified_unit_header_is_a_structure_mismatch():
    forecasts, rejections = mapped(sheets(growth=[headline_gdp(header="% q/q sa")]))
    assert by(forecasts, "gdp") == []
    assert (2, 1, 2) in at(rejections, "mapping_structure_mismatch")


def test_whitespace_only_differences_still_match():
    growth = [("  Real   GDP ", headline_gdp()[1])]
    forecasts, _ = mapped(sheets(growth=growth))
    assert len(by(forecasts, "gdp")) == 3


def test_an_entry_on_an_unreadable_sheet_is_a_structure_mismatch():
    s = sheets()
    s[1] = data_sheet(
        GROWTH, [headline_gdp()], notes=(AS_AT,)
    )  # no legend: forecast_marker_missing
    forecasts, rejections = mapped(s)
    assert by(forecasts, "gdp") == []
    assert at(rejections, "forecast_marker_missing") == [(2, None, None)]
    assert (2, 1, 2) in at(rejections, "mapping_structure_mismatch")


def test_an_entry_naming_another_indicators_column_is_refused():
    wrong = cpi_entry(sheet=2, sheet_name=GROWTH, block=1, block_title="Real GDP", column="B", unit_header="% q/q",
                      basis="quarterly")  # fmt: skip
    forecasts, rejections = mapped(doc=manifest(series=[wrong]))
    assert by(forecasts, "gdp") == by(forecasts, "cpi_inflation") == []
    assert at(rejections, "mapping_indicator_mismatch") == [(2, 1, 2)]


# --- every existing rule still applies to listed columns ------------------------------------------------------------


def test_a_basis_the_column_does_not_state_is_a_basis_mismatch():
    forecasts, rejections = mapped(doc=manifest(series=[gdp_entry(basis="annual")]))
    assert by(forecasts, "gdp") == []
    assert at(rejections, "mapping_basis_mismatch") == [(2, 1, 2)]


def test_a_gdp_column_with_no_stated_basis_is_refused_whatever_the_manifest_says():
    growth = [headline_gdp(header="%")]
    doc = manifest(series=[gdp_entry(unit_header="%")])
    forecasts, rejections = mapped(sheets(growth=growth), doc)
    assert by(forecasts, "gdp") == []
    assert at(rejections, "mapping_basis_mismatch") == [(2, 1, 2)]


def test_an_unsupported_unit_stays_refused():
    growth = [headline_gdp(header="Index q/q")]
    forecasts, rejections = mapped(
        sheets(growth=growth), manifest(series=[gdp_entry(unit_header="Index q/q")])
    )
    assert by(forecasts, "gdp") == []
    assert at(rejections, "unsupported_unit") == [(2, 1, 2)]


def test_unit_evidence_that_conflicts_with_the_header_is_refused():
    prices = [("Unemployment rate", [("basis points", series(UNEMP))])]
    doc = manifest(series=[unemployment_entry(block=1, column="B", unit_header="basis points")])
    forecasts, rejections = mapped(sheets(prices=prices), doc)
    assert by(forecasts, "unemployment") == []
    assert at(rejections, "contradictory_unit") == [(3, 1, 2)]


@pytest.mark.parametrize(
    "evidence",
    [
        None,  # absent
        {"sheet": 3, "cell": "A14", "text": UNIT_NOTE},  # wrong cell
        {"sheet": 3, "cell": UNIT_CELL, "text": "Unemployment rate in per cent"},  # wrong text
        {"sheet": 3, "cell": "Z99", "text": UNIT_NOTE},  # an empty cell
    ],
)
def test_unemployment_without_verified_unit_evidence_stays_unit_unstated(evidence):
    forecasts, rejections = mapped(
        doc=manifest(series=[unemployment_entry(unit_evidence=evidence)])
    )
    assert by(forecasts, "unemployment") == []
    assert at(rejections, "unit_unstated") == [(3, 3, 4)]


def test_unit_evidence_must_be_a_note_below_the_table():
    # Prices C2 is another column's unit header; it names percent but is not a note under the table.
    evidence = {"sheet": 3, "cell": "C2", "text": "Annual % change"}
    forecasts, rejections = mapped(
        doc=manifest(series=[unemployment_entry(unit_evidence=evidence)])
    )
    assert by(forecasts, "unemployment") == []
    assert at(rejections, "unit_unstated") == [(3, 3, 4)]


def test_an_editorial_review_drops_the_sheet_name_only_from_the_unknown_word_rule():
    forecasts, _ = mapped()
    f = by(forecasts, "gdp")[0]
    # A sheet name that states another basis still contradicts the column, review or not.
    evidence = {**f.evidence, "caption": "Annual Tracker", "caption_review": {**f.evidence["caption_review"], "sheet_name": "Annual Tracker"}}  # fmt: skip
    assert stored_context_rejection(f.label, evidence) == "contradictory_period"


def test_a_caption_review_counts_only_on_mapped_evidence():
    forecasts, _ = mapped()
    f = by(forecasts, "gdp")[0]
    evidence = {k: v for k, v in f.evidence.items() if k != "mapping_entry"}
    assert stored_context_rejection(f.label, evidence) == "unsupported_context"


def test_unit_evidence_whose_text_names_no_percent_stays_unit_unstated():
    notes = (LEGEND, AS_AT, "Unemployment rate")
    evidence = {"sheet": 3, "cell": UNIT_CELL, "text": "Unemployment rate"}
    forecasts, rejections = mapped(sheets(prices_notes=notes), manifest(series=[unemployment_entry(unit_evidence=evidence)]))  # fmt: skip
    assert by(forecasts, "unemployment") == []
    assert at(rejections, "unit_unstated") == [(3, 3, 4)]


@pytest.mark.parametrize(
    "context",
    [
        [],  # not reviewed
        [{"sheet": 2, "sheet_name": GROWTH, "classification": "substantive"}],
        [
            {"sheet": 2, "sheet_name": "Growth Monitor", "classification": "editorial"}
        ],  # a different name
        [{"sheet": 3, "sheet_name": GROWTH, "classification": "editorial"}],  # a different position
    ],
)
def test_a_sheet_name_not_reviewed_as_editorial_keeps_the_context_refusal(context):
    forecasts, rejections = mapped(doc=manifest(sheet_context=context))
    assert by(forecasts, "gdp") == []
    assert at(rejections, "unsupported_context") == [(2, 1, 2)]


def test_a_title_qualifier_is_never_dropped_by_the_sheet_review():
    growth = [("Real GDP scenario", headline_gdp()[1])]
    forecasts, rejections = mapped(sheets(growth=growth), manifest(series=[gdp_entry(block_title="Real GDP scenario")]))  # fmt: skip
    assert by(forecasts, "gdp") == []
    assert rejections


def test_a_wrong_forecast_boundary_is_still_refused():
    growth = [headline_gdp(bold_rows=[5, 7])]  # a gap inside the bold tail
    forecasts, rejections = mapped(sheets(growth=growth))
    assert by(forecasts, "gdp") == []
    assert at(rejections, "forecast_boundary_unclear") == [(2, 1, 2)]


def test_a_bold_history_cell_is_still_refused():
    growth = [headline_gdp(bold_rows=[1, 5, 6, 7])]
    forecasts, rejections = mapped(sheets(growth=growth))
    assert by(forecasts, "gdp") == []
    assert at(rejections, "forecast_boundary_unclear") == [(2, 1, 2)]


def test_third_party_attribution_is_kept():
    notes = (LEGEND, AS_AT, "Source: Treasury")
    forecasts, _ = mapped(sheets(growth_notes=notes))
    assert {f.author_role for f in by(forecasts, "gdp")} == {"third_party"}


# --- confirmation code and stored revalidation ------------------------------------------------------------------------


def test_the_confirmation_code_covers_the_mapping_hash():
    forecasts, _ = mapped()
    first = parse_mapping(body(manifest()))
    other = parse_mapping(body(manifest(decided_on="2026-11-23")))
    code = candidate_hash8(forecasts, mapping_sha256=first.sha256)
    assert code != candidate_hash8(forecasts)
    assert code != candidate_hash8(forecasts, mapping_sha256=other.sha256)
    assert code == candidate_hash8(forecasts, mapping_sha256=first.sha256)


def test_stored_revalidation_honours_only_a_matching_editorial_review():
    forecasts, _ = mapped()
    f = by(forecasts, "gdp")[0]
    assert stored_context_rejection(f.label, f.evidence) is None
    tampered = [
        {**f.evidence, "mapping_sha256": "e" * 64},
        {
            **f.evidence,
            "caption_review": {**f.evidence["caption_review"], "classification": "substantive"},
        },
        {**f.evidence, "caption_review": {**f.evidence["caption_review"], "sheet_name": "Other"}},
        {**f.evidence, "caption": "Growth Monitor"},
        {k: v for k, v in f.evidence.items() if k != "mapping_sha256"},
        {**f.evidence, "caption_review": "editorial"},
    ]
    for evidence in tampered:
        assert stored_context_rejection(f.label, evidence) == "unsupported_context"


# --- building the manifest from positions (the owner's `tables map`) ------------------------------------------------


def test_the_manifest_is_built_from_positions_only():
    wb = workbook(sheets())
    raw = mapping_from_positions(
        wb, workbook_sha256=SHA, decided_on="2026-11-22",
        series=[("gdp", 2, 1, "B", "quarterly"), ("cpi_inflation", 3, 1, "B", "annual"),
                ("unemployment", 3, 3, "D", "quarterly")],
        unit_evidence=(3, UNIT_CELL), sheet_context=[(2, "editorial")], published=None,
    )  # fmt: skip
    assert json.loads(raw) == manifest()
    assert parse_mapping(raw).sha256


def test_the_built_manifest_records_the_publication_cell():
    raw = mapping_from_positions(
        workbook(sheets()), workbook_sha256=SHA, decided_on="2026-11-22", series=[("gdp", 2, 1, "B", "quarterly")],
        unit_evidence=None, sheet_context=[], published=("2026-11-05", 3, "A14"),
    )  # fmt: skip
    assert json.loads(raw)["published_on"] == {
        "date": "2026-11-05",
        "sheet": 3,
        "cell": "A14",
        "text": AS_AT,
    }


@pytest.mark.parametrize(
    "kw",
    [
        {"series": [("gdp", 9, 1, "B", "quarterly")]},  # no such sheet
        {"series": [("gdp", 2, 2, "B", "quarterly")]},  # column B is not in block 2
        {"series": [("gdp", 2, 1, "Z", "quarterly")]},  # no such column
        {
            "series": [("unemployment", 3, 3, "D", "quarterly")],
            "unit_evidence": (3, "Z99"),
        },  # empty cell
        {"series": [("gdp", 2, 1, "B", "quarterly")], "sheet_context": [(9, "editorial")]},
        {"series": [("gdp", 2, 1, "B", "quarterly")], "published": ("2026-11-05", 3, "Z99")},
    ],
)
def test_a_position_that_is_not_in_the_workbook_is_refused(kw):
    args = {"unit_evidence": None, "sheet_context": [], "published": None, **kw}
    with pytest.raises(MappingRefused) as caught:
        mapping_from_positions(
            workbook(sheets()), workbook_sha256=SHA, decided_on="2026-11-22", **args
        )
    assert caught.value.code == "mapping_position_invalid"


def test_a_built_manifest_that_would_be_invalid_is_refused():
    with pytest.raises(MappingRefused) as caught:
        mapping_from_positions(
            workbook(sheets()), workbook_sha256=SHA, decided_on="2026-11-22",
            series=[("ocr", 2, 1, "B", "quarterly")], unit_evidence=None, sheet_context=[], published=None,
        )  # fmt: skip
    assert caught.value.code == "mapping_invalid"

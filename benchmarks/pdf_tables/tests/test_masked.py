"""The masked diagnostics never carry document text or figures: the output schema refuses anything but counts, and a
canary document's words and figures never appear in the emitted output."""

import hashlib
import json
import sqlite3

import pytest

from pdfbench import synth
from pdfbench.masked import _agrees, _value_triples, diagnose, emit
from pdfbench.model import BenchTable
from pdfbench.run_masked import VersionUnavailable, load_version

CANARY_LABELS = ["Vrkzal", "Wqpxom", "Yxzqub"]
CANARY_HEADERS = ["Qzjx26f", "Qzjx27f", "Qzjx28f"]
CANARY_VALUES = [["7.913", "8.137", "9.371"], ["6.529", "5.843", "4.761"], ["3.917", "2.683", "1.459"]]
CANARY_NOTE = "Source: Kzqwvbank"


def _canary_pdf() -> bytes:
    page = synth._Page()
    page.text(60, 730, "Table 9: Zyxwvut projections", 9)
    synth._grid(
        page,
        top=700,
        label_x=60,
        first_right=250,
        pitch=50,
        headers=CANARY_HEADERS,
        labels=CANARY_LABELS,
        values=CANARY_VALUES,
        hrules=True,
    )
    page.text(250 + 0.3, 700 - synth.LEAD + 3, "1", synth.SMALL)  # a raised marker fused after the first value
    page.text(60, 640, CANARY_NOTE)
    return synth._render([page], "canary")


@pytest.fixture(scope="module")
def emitted() -> str:
    return emit(diagnose(_canary_pdf(), [1]))


def test_output_is_json_of_counts(emitted):
    data = json.loads(emitted)
    assert set(data) == {"pages", "parsers"}
    assert data["parsers"]["existing"]["pages"]["1"]["tables"] == 1


def test_no_canary_word_reaches_the_output(emitted):
    for word in [*CANARY_LABELS, *CANARY_HEADERS, "Kzqwvbank", "Zyxwvut", "SYNTHETIC"]:
        assert word not in emitted
        assert word.lower() not in emitted.lower()


def test_no_canary_figure_reaches_the_output(emitted):
    for value in [v for row in CANARY_VALUES for v in row] + ["7.9131"]:
        assert value not in emitted


def test_fused_marker_is_counted_without_its_text(emitted):
    page = json.loads(emitted)["pages"]["1"]
    assert page["value_marker_sites"] == 1


def test_page_graphics_are_counted(emitted):
    assert json.loads(emitted)["pages"]["1"]["lines"] == 3


def test_existing_agrees_with_itself(emitted):
    page = json.loads(emitted)["parsers"]["existing"]["pages"]["1"]
    assert page["agreement_with_existing"] == page["existing_value_cells"] > 0


@pytest.mark.parametrize(
    "bad",
    [
        {"pages": {"1": {"lines": "Vrkzal"}}},  # a string value
        {"pages": {"1": {"Vrkzal": 1}}},  # an unknown key
        {"parsers": {"Vrkzal": {}}},  # an unknown parser
        {"parsers": {"existing": {"error": "Kzqwv"}}},  # an error that is not a fixed code
        {"pages": {"1": {"shapes": [["Vrkzal", 3]]}}},  # a string inside a list
        {"pages": {"page 1": {}}},  # a page key that is not a number
    ],
)
def test_emit_refuses_anything_but_counts(bad):
    with pytest.raises(ValueError):
        emit(bad)


def test_emit_accepts_fixed_error_codes():
    assert json.loads(emit({"parsers": {"camelot_stream": {"error": "timeout", "seconds": 1.0}}}))


# --- version loading: fail closed, never print what it read -------------------------------------------------------


def _db(tmp_path, body: bytes, sha: str) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE research_institution (id INTEGER PRIMARY KEY, key TEXT);
        CREATE TABLE research_publication (id INTEGER PRIMARY KEY, institution_id INT, canonical_url TEXT);
        CREATE TABLE raw_artifact (id INTEGER PRIMARY KEY, path TEXT, sha256 TEXT);
        CREATE TABLE research_document_version (id INTEGER PRIMARY KEY, publication_id INT, raw_artifact_id INT,
            title TEXT, format TEXT, purged_at TEXT, acquisition TEXT);
        INSERT INTO research_institution VALUES (1, 'synthetic');
        INSERT INTO research_publication VALUES (1, 1, 'https://example.invalid/x.pdf');
        """
    )
    real = hashlib.sha256(body).hexdigest()
    rel = f"{real[:2]}/{real}"  # the only path shape the artifact store reads
    (tmp_path / "raw" / real[:2]).mkdir(parents=True)
    (tmp_path / "raw" / rel).write_bytes(body)
    conn.execute("INSERT INTO raw_artifact VALUES (1, ?, ?)", (rel, sha))
    conn.execute("INSERT INTO research_document_version VALUES (7, 1, 1, 't', 'pdf', NULL, 'manual_import')")
    return conn


def _allow(row, registry):
    return None, object()


def test_load_version_returns_the_verified_bytes(tmp_path):
    body = _canary_pdf()
    conn = _db(tmp_path, body, hashlib.sha256(body).hexdigest())
    assert load_version(conn, 7, tmp_path / "raw", {}, refusal=_allow) == body


def test_load_version_refuses_a_hash_mismatch(tmp_path):
    conn = _db(tmp_path, _canary_pdf(), "0" * 64)
    with pytest.raises(VersionUnavailable, match="^hash_mismatch$"):
        load_version(conn, 7, tmp_path / "raw", {}, refusal=_allow)


def test_load_version_refuses_what_the_registry_refuses(tmp_path):
    body = _canary_pdf()
    conn = _db(tmp_path, body, hashlib.sha256(body).hexdigest())
    with pytest.raises(VersionUnavailable, match="^refused$"):
        load_version(conn, 7, tmp_path / "raw", {}, refusal=lambda row, reg: ("source not permitted", None))


def test_load_version_refuses_an_unknown_version(tmp_path):
    body = _canary_pdf()
    conn = _db(tmp_path, body, hashlib.sha256(body).hexdigest())
    with pytest.raises(VersionUnavailable, match="^refused$"):
        load_version(conn, 99, tmp_path / "raw", {})


# --- agreement with the existing grid: compare structure, not the marker or line-break form -----------------------

EXISTING = [BenchTable(1, (0, 0, 1, 1), [["", "Current (11 Nov)"], ["Prices¹", "2.5"]], header_rows=1)]


def test_existing_label_marker_does_not_block_agreement():
    other = [BenchTable(1, (0, 0, 1, 1), [["", "Current (11 Nov)"], ["1", ""], ["Prices", "2.5"]])]
    assert all(_agrees(other, *t) for t in _value_triples(EXISTING))


def test_stacked_header_split_over_two_rows_agrees():
    other = [BenchTable(1, (0, 0, 1, 1), [["", "Current"], ["", "(11 Nov)"], ["Prices", "2.5"]])]
    assert all(_agrees(other, *t) for t in _value_triples(EXISTING))


def test_value_under_another_header_does_not_agree():
    other = [BenchTable(1, (0, 0, 1, 1), [["", "Dec-26"], ["Prices", "2.5"]])]
    assert not any(_agrees(other, *t) for t in _value_triples(EXISTING))


def test_unreproduced_cells_are_reported_as_grid_positions_only(emitted):
    page = json.loads(emitted)["parsers"]["existing"]["pages"]["1"]
    assert page["unreproduced_existing_cells"] == []


def test_unreproduced_positions_name_table_row_and_column():
    from pdfbench.masked import _unreproduced

    other = [BenchTable(1, (0, 0, 1, 1), [["", "Dec-26"], ["Prices", "2.5"]])]
    assert _unreproduced(other, EXISTING) == [[0, 1, 1]]


def test_unreproduced_position_survives_a_blank_cell_earlier_in_the_row():
    from pdfbench.masked import _unreproduced

    existing = [BenchTable(1, (0, 0, 1, 1), [["", "Dec-26", "Mar-27"], ["Prices", "", "2.5"]])]
    other = [BenchTable(1, (0, 0, 1, 1), [["", "Dec-26", "Mar-27"], ["Prices", "", "9.9"]])]
    assert _unreproduced(other, existing) == [[0, 1, 2]]
    assert _unreproduced(existing, existing) == []


def test_unreproduced_reasons_separate_label_header_and_value():
    from pdfbench.masked import _reasons

    existing = [BenchTable(1, (0, 0, 1, 1), [["", "Dec-26", "Mar-27", "Jun-27"], ["Prices¹", "2.5", "2.6", "2.7"]])]
    other = [
        BenchTable(
            1,
            (0, 0, 1, 1),
            [["", "Dec-26", "Jun-27", "Mar-27"], ["1", "2.5", "", ""], ["Prices", "", "2.6", "2.7"]],
        )
    ]
    # 2.5 sits under its header but not on the label's row; 2.6 and 2.7 sit on the label's row under the wrong header.
    assert _reasons(other, existing) == {"label_mismatch": 1, "header_mismatch": 2, "value_missing": 0}
    assert _reasons(existing, existing) == {"label_mismatch": 0, "header_mismatch": 0, "value_missing": 0}


# --- review fixes: no side channel around emit --------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"parsers": {"existing": {"pages": {"5": {"2027": 3}}}}},  # a year header as a metric key
        {"pages": {"5": {"2026": 1}}},  # a digit key below a page
        {"parsers": {"existing": {"2026": 1}}},  # a digit key outside a pages map
    ],
)
def test_digit_keys_are_allowed_only_as_page_numbers(bad):
    with pytest.raises(ValueError):
        emit(bad)


BROKEN = b"%PDF-1.4\n1 0 obj << /Kids [ (Kzqwvcanary) 9 0 R ] >> stream\n(Kzqwvcanary) Tj\nendstream\ntrailer << /Root 1 0 R >>\n"


def test_a_broken_document_prints_nothing_on_either_stream(capfd):
    from pdfbench.masked import safe_diagnose

    assert safe_diagnose(BROKEN, [1]) == {"error": "error"}
    out, err = capfd.readouterr()
    assert out == "" and err == ""


def test_parser_children_print_nothing_on_either_stream(capfd):
    from pdfbench.adapters import PARSERS, run

    for name in sorted(PARSERS):
        run(name, BROKEN, [1])
    out, err = capfd.readouterr()
    assert "Kzqwvcanary" not in out + err
    assert out == "" and err == ""


def test_a_value_marker_does_not_block_agreement_but_a_fused_digit_does():
    existing = [BenchTable(1, (0, 0, 1, 1), [["", "2026f"], ["Prices", "2.5¹"]])]
    separated = [BenchTable(1, (0, 0, 1, 1), [["", "2026f"], ["", "1"], ["Prices", "2.5"]])]
    fused = [BenchTable(1, (0, 0, 1, 1), [["", "2026f"], ["Prices", "2.51"]])]
    assert all(_agrees(separated, *t) for t in _value_triples(existing))
    assert not any(_agrees(fused, *t) for t in _value_triples(existing))


def test_values_under_a_collapsed_header_do_not_agree():
    existing = [BenchTable(1, (0, 0, 1, 1), [["", "2026f", "2027f"], ["Prices", "2.5", "2.4"]])]
    collapsed = [BenchTable(1, (0, 0, 1, 1), [["", "2026f 2027f"], ["Prices", "2.5"], ["Prices", "2.4"]])]
    assert not any(_agrees(collapsed, *t) for t in _value_triples(existing))


def test_a_foreign_header_is_matched_as_a_whole_token():
    existing = [BenchTable(1, (0, 0, 1, 1), [["", "2026f", "2026"], ["Prices", "2.5", "2.4"]])]
    assert all(_agrees(existing, *t) for t in _value_triples(existing))


@pytest.mark.parametrize(
    ("headers", "collapsed"),
    [(["2026", "2027"], "2026f 2027f"), (["Dec", "Jan"], "Dec-26 Jan-27")],
)
def test_a_collapsed_header_with_suffixed_periods_does_not_agree(headers, collapsed):
    existing = [BenchTable(1, (0, 0, 1, 1), [["", *headers], ["Prices", "2.5", "2.4"]])]
    other = [BenchTable(1, (0, 0, 1, 1), [["", collapsed], ["Prices", "2.5"], ["Prices", "2.4"]])]
    assert not any(_agrees(other, *t) for t in _value_triples(existing))


# A value marker kept as a separate digit in the cell ("2.5 1") is the same figure as "2.5¹" (PR #65 review).
MARKED = [BenchTable(1, (0, 0, 1, 1), [["", "2026f"], ["Prices", "2.5¹"]])]


def _one(cell, header="2026f"):
    return [BenchTable(1, (0, 0, 1, 1), [["", header], ["Prices", cell]])]


@pytest.mark.parametrize("cell", ["2.5¹", "2.5", "2.5 1", "2.5 ¹", " 2.5  1 "])
def test_a_separable_value_marker_agrees(cell):
    from pdfbench.masked import _reasons, _unreproduced

    assert all(_agrees(_one(cell), *t) for t in _value_triples(MARKED))
    assert _unreproduced(_one(cell), MARKED) == []
    assert _reasons(_one(cell), MARKED) == {"label_mismatch": 0, "header_mismatch": 0, "value_missing": 0}


@pytest.mark.parametrize("cell", ["2.51", "2.5 2", "2.5 1 1", "2.5 12"])
def test_a_fused_or_foreign_marker_digit_does_not_agree(cell):
    from pdfbench.masked import _reasons

    assert not any(_agrees(_one(cell), *t) for t in _value_triples(MARKED))
    assert _reasons(_one(cell), MARKED)["value_missing"] == 1


def test_an_unmarked_value_does_not_agree_with_a_trailing_digit():
    from pdfbench.masked import _reasons

    plain = [BenchTable(1, (0, 0, 1, 1), [["", "2026f"], ["Prices", "2.5"]])]
    assert not any(_agrees(_one("2.5 1"), *t) for t in _value_triples(plain))
    assert _reasons(_one("2.5 1"), plain)["value_missing"] == 1


@pytest.mark.parametrize("cell", ["2.5¹", "2.5 1"])
def test_a_marked_value_under_another_header_is_a_header_mismatch(cell):
    from pdfbench.masked import _reasons

    assert _reasons(_one(cell, header="2027f"), MARKED) == {
        "label_mismatch": 0,
        "header_mismatch": 1,
        "value_missing": 0,
    }


# One parsed cell reproduces at most one existing cell (PR #65 review).
def _prices(*cells, header="2026f"):
    return BenchTable(1, (0, 0, 1, 1), [["", header], *(["Prices", c] for c in cells)])


def _agreement(tables, existing):
    from pdfbench.masked import _page_metrics

    m = _page_metrics(tables, existing, [], [], 100.0)
    return m["agreement_with_existing"], m["unreproduced_existing_cells"], m["unreproduced_reasons"]


def test_one_parsed_cell_reproduces_one_of_two_identical_existing_cells():
    agree, missing, reasons = _agreement([_prices("2.5")], [_prices("2.5"), _prices("2.5")])
    assert agree == 1 and len(missing) == 1
    assert reasons == {"label_mismatch": 0, "header_mismatch": 0, "value_missing": 1}


def test_two_parsed_cells_reproduce_two_identical_existing_cells():
    assert _agreement([_prices("2.5"), _prices("2.5")], [_prices("2.5"), _prices("2.5")])[:2] == (2, [])
    assert _agreement([_prices("2.5", "2.5")], [_prices("2.5", "2.5")])[:2] == (2, [])


def test_a_duplicate_inside_one_existing_table_needs_its_own_cell():
    agree, missing, _ = _agreement([_prices("2.5")], [_prices("2.5", "2.5")])
    assert agree == 1 and len(missing) == 1


def test_agreement_does_not_depend_on_parsed_table_order():
    existing = [_prices("2.5¹"), _prices("2.5")]
    tables = [_prices("2.5"), _prices("2.5 1"), _prices("2.4")]
    first = _agreement(tables, existing)
    assert first[0] == 2
    assert _agreement(tables[::-1], existing) == first


def test_unreproduced_cells_match_their_reasons_on_random_pages():
    import random

    from pdfbench.masked import _reasons, _unreproduced

    rng = random.Random(5)
    for _ in range(300):
        existing = [
            _prices(*rng.choices(["2.5", "2.4", "2.5¹"], k=rng.randint(1, 3))) for _ in range(rng.randint(1, 3))
        ]
        tables = [
            _prices(
                *rng.choices(["2.5", "2.4", "2.5 1", ""], k=rng.randint(0, 3)), header=rng.choice(["2026f", "2027f"])
            )
            for _ in range(rng.randint(0, 3))
        ]
        agree, missing, reasons = _agreement(tables, existing)
        total = sum(len(e.grid) - 1 for e in existing)
        assert agree + len(missing) == total == agree + sum(reasons.values())
        assert missing == _unreproduced(tables, existing) and reasons == _reasons(tables, existing)
        assert agree <= sum(1 for t in tables for row in t.grid[1:] for c in row[1:] if c)
        assert _agreement(tables[::-1], existing)[0] == agree


# A marker site keeps the figure's sign, so a fused "-2.51" is counted (PR #65 review).
def _char(text, x0, x1, size=10.0):
    return {"text": text, "x0": x0, "x1": x1, "size": size, "top": 0.0, "bottom": size}


@pytest.mark.parametrize("sign", ["-", "−", "–", "+"])
def test_a_marker_site_keeps_the_sign_of_its_figure(sign):
    from pdfbench.masked import _marker_sites

    chars = [_char(sign, 0, 4), _char("2", 4, 10), _char(".", 10, 12), _char("5", 12, 18), _char("1", 18.5, 22, 6.0)]
    assert _marker_sites(chars) == ([(f"{sign}2.5", "1")], 0)


def test_a_sign_set_apart_from_the_figure_is_not_part_of_it():
    from pdfbench.masked import _marker_sites

    chars = [_char("-", 0, 2), _char("2", 8, 14), _char(".", 14, 16), _char("5", 16, 22), _char("1", 22.5, 26, 6.0)]
    assert _marker_sites(chars) == ([("2.5", "1")], 0)


def test_a_fused_marker_on_a_negative_figure_is_counted():
    from pdfbench.masked import _page_metrics

    m = _page_metrics([_prices("-2.51")], None, [("-2.5", "1")], [], 100.0)
    assert m["fused_marker_cells"] == 1


def test_a_dash_after_a_figure_is_a_range_not_a_sign():
    from pdfbench.masked import _marker_sites

    chars = [_char(c, 6 * k, 6 * k + 6) for k, c in enumerate("2.5–3.0")] + [_char("1", 42.5, 46, 6.0)]
    assert _marker_sites(chars) == ([("3.0", "1")], 0)


def test_a_parsed_cell_reproducing_one_value_is_not_evidence_for_another():
    from pdfbench.masked import _reasons

    existing = [BenchTable(1, (0, 0, 1, 1), [["", "2026f"], ["Prices", "2.5"], ["Jobless rate", "2.5"]])]
    agree, missing, reasons = _agreement([_prices("2.5")], existing)
    assert (agree, missing) == (1, [[0, 2, 1]])
    assert reasons == {"label_mismatch": 0, "header_mismatch": 0, "value_missing": 1}
    assert _reasons([_prices("2.5", "2.5")], existing)["label_mismatch"] == 1  # a second, unused copy is evidence

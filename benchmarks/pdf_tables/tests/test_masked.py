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

import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from tests import synth
from xlsxinspect.guard import emit
from xlsxinspect.inspect import inspect

BACKEND = Path(__file__).resolve().parents[3] / "backend" / "src" / "nzstats" / "research" / "table_forecast.py"


@pytest.fixture
def book(tmp_path):
    return synth.save(synth.forecast_book(), tmp_path / "f.xlsx")


def test_reports_sheet_states_and_dimensions_in_workbook_order(book):
    r = inspect(book)
    assert r["status"] == "ok"
    assert [s["state"] for s in r["sheets"]] == ["visible", "hidden", "very_hidden"]
    first = r["sheets"][0]
    assert (first["rows"], first["cols"]) == (10, 4)
    assert first["merged"] == 1 and first["comments"] == 1


def test_counts_indicator_labels_periods_and_markers_with_production_vocabulary(book):
    s = inspect(book)["sheets"][0]
    assert s["indicator_labels"] == {"ocr": 1, "cpi_inflation": 1, "gdp": 0, "unemployment": 0}
    assert s["label_columns"] == [1]
    assert s["period_headers"] == 3
    assert s["period_header_rows"] == 1 and s["period_header_cols"] == 3
    assert s["period_kinds"] == {"quarter": 0, "month_end": 3, "year_to": 0, "calendar": 0}
    assert s["forecast_markers"] == 3  # "Forecast" group header plus two trailing f
    assert s["actual_markers"] == 1
    assert s["dates"] == 1


def test_counts_numbers_and_percent_formats_without_reading_them_out(book):
    s = inspect(book)["sheets"][0]
    assert s["numeric"] == 7
    assert s["percent_format"] == 3
    assert inspect(book)["sheets"][1]["year_like_numbers"] == 1


def test_counts_attribution_notice_and_unit_hints(book):
    s = inspect(book)["sheets"][0]
    assert s["anz_mentions"] == 1
    assert s["other_forecaster_mentions"] == 0
    assert s["notice_cells"] == 1
    assert s["unit_hints"]["percent"] == 2  # "(%)" and "% change"
    assert s["unit_hints"]["annual"] == 1


def test_reports_workbook_metadata_as_numbers(book):
    with zipfile.ZipFile(book) as z:
        core = z.read("docProps/core.xml").decode()
    core = re.sub(r"(<dcterms:modified[^>]*>)[^<]*", r"\g<1>2026-11-11T09:30:00Z", core)  # openpyxl stamps save time
    synth.rewrite(book, {"docProps/core.xml": core.encode()})
    w = inspect(book)["workbook"]
    assert w["sheets"] == 3
    assert w["has_modified"] is True and w["modified_ymd"] == [2026, 11, 11]


def test_formula_without_cached_value_is_counted_as_uncached(tmp_path):
    wb = Workbook()
    wb.active["A1"] = 1
    wb.active["B1"] = "=A1+1"
    r = inspect(synth.save(wb, tmp_path / "f.xlsx"))
    s = r["sheets"][0]
    assert (s["formulas"], s["formulas_cached"], s["formulas_uncached"]) == (1, 0, 1)


def test_formula_with_cached_value_is_counted_as_cached(tmp_path):
    wb = Workbook()
    wb.active["A1"] = 1
    wb.active["B1"] = "=A1+1"
    path = synth.with_cached_formula(synth.save(wb, tmp_path / "f.xlsx"), "B1", "2")
    s = inspect(path)["sheets"][0]
    assert (s["formulas"], s["formulas_cached"], s["formulas_uncached"]) == (1, 1, 0)


def test_external_link_parts_and_formulas_are_flagged_and_never_followed(tmp_path):
    wb = Workbook()
    wb.active["A1"] = "='[1]Other'!A1"
    path = synth.save(wb, tmp_path / "f.xlsx")
    synth.rewrite(path, {}, add={"xl/externalLinks/externalLink1.xml": b"<externalLink/>"})
    r = inspect(path)
    assert r["archive"]["external_link_parts"] == 1
    assert r["sheets"][0]["formulas_external"] == 1


def test_macro_part_is_flagged(tmp_path, book):
    synth.rewrite(book, {}, add={"xl/vbaProject.bin": b"\0" * 16})
    assert inspect(book)["archive"]["vba_part"] is True


@pytest.mark.parametrize(
    "mutate,flag",
    [
        (
            lambda p: synth.rewrite(
                p, {"xl/worksheets/sheet1.xml": b'<!DOCTYPE x [<!ENTITY a "b">]>' + synth.sheet1(p)}
            ),
            "xml_declarations",
        ),
        (lambda p: synth.rewrite(p, {}, add={"../escape.txt": b"x"}), "unsafe_path"),
        (lambda p: p.write_bytes(b"not a zip"), "not_zip"),
    ],
)
def test_unsafe_archives_are_refused_before_openpyxl_reads_them(book, mutate, flag, monkeypatch):
    import xlsxinspect.inspect as mod

    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("openpyxl must not open a refused archive"))
    mutate(book)
    r = inspect(book)
    assert r["status"] == "refused"
    assert r["archive"][flag] is True
    assert "sheets" not in r


def test_oversized_archive_is_refused(book, monkeypatch):
    import xlsxinspect.inspect as mod

    monkeypatch.setattr(mod, "MAX_UNPACKED", 10)
    r = inspect(book)
    assert r["status"] == "refused" and r["archive"]["over_limit"] is True


def test_a_reader_failure_is_a_fixed_code_with_no_message(book, monkeypatch):
    import xlsxinspect.inspect as mod

    def boom(*a, **k):
        raise RuntimeError(synth.SECRET_LABEL)

    monkeypatch.setattr(mod, "load_workbook", boom)
    r = inspect(book)
    assert r["status"] == "error"
    assert synth.SECRET_LABEL not in emit(r)


def test_output_carries_the_file_hash_and_no_document_text_or_figures(book):
    out = emit(inspect(book))
    assert json.loads(out)["sha256"] == hashlib.sha256(book.read_bytes()).hexdigest()
    for leak in (
        synth.SECRET_LABEL,
        "987.65",
        "Synthetic forecasts",
        "helper",
        "Fictional",
        "OCR",
        "Sep-26",
        "2.25",
        "tester",
    ):
        assert leak not in out


def test_sheet_xml_is_the_part_the_synthetic_helpers_edit(book):
    with zipfile.ZipFile(book) as z:
        assert "xl/worksheets/sheet1.xml" in z.namelist()


def test_indicator_vocabulary_matches_production():
    """The inspector copies table_forecast's indicator and forecaster vocabulary; a drift must fail here."""
    from xlsxinspect.inspect import INDICATORS, OTHER_FORECASTERS

    source = BACKEND.read_text()
    block = source[source.index("_INDICATORS: dict") : source.index("_RATE_INDICATORS")]
    prod = dict(re.findall(r'"(\w+)": re\.compile\(r"((?:[^"\\]|\\.)*)"', block))
    assert {k: p.pattern for k, p in INDICATORS.items()} == prod
    names = re.findall(r'"([^"]+)"', block[block.index("_OTHER_FORECASTERS") :])
    assert tuple(names) == OTHER_FORECASTERS


# ---------------------------------------------------------------- review fixes (Phase 4AN independent review)


def _corrupt_member(path):
    """Flip bytes inside the compressed stream of sheet1 so reading it raises (bad CRC or zlib error)."""
    raw = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as z:
        info = z.getinfo("xl/worksheets/sheet1.xml")
    start = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    for i in range(start + 2, start + 12):
        raw[i] ^= 0xFF
    path.write_bytes(bytes(raw))


def test_a_corrupt_member_is_a_fixed_code_not_an_exception(book):
    _corrupt_member(book)
    r = inspect(book)
    assert r["status"] == "refused" and r["archive"]["unreadable"] is True
    emit(r)


def test_inspect_takes_the_bytes_it_was_given(book):
    raw = book.read_bytes()
    book.write_bytes(b"changed after the hash check")
    r = inspect(book, raw=raw)
    assert r["status"] == "ok" and r["sha256"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
def test_a_doctype_in_a_utf16_part_is_refused(book, encoding, monkeypatch):
    import xlsxinspect.inspect as mod

    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("must not open"))
    xml = synth.sheet1(book).decode().replace('<?xml version="1.0" encoding="UTF-8"?>', "", 1)
    part = f'<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY a "b">]>{xml}'.encode(encoding)
    synth.rewrite(book, {"xl/worksheets/sheet1.xml": part})
    r = inspect(book)
    assert r["status"] == "refused" and r["archive"]["xml_declarations"] is True


def test_a_doctype_in_a_part_with_any_extension_is_refused(book, monkeypatch):
    import xlsxinspect.inspect as mod

    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("must not open"))
    synth.rewrite(book, {}, add={"xl/worksheets/sheet9.dat": b'<!DOCTYPE x [<!ENTITY a "b">]><x/>'})
    assert inspect(book)["archive"]["xml_declarations"] is True


def test_checks_not_run_after_an_early_refusal_are_reported_as_unknown(book, monkeypatch):
    import xlsxinspect.inspect as mod

    monkeypatch.setattr(mod, "MAX_MEMBERS", 1)
    a = inspect(book)["archive"]
    assert a["over_limit"] is True and a["xml_declarations"] is None and a["macro_content_type"] is None


def test_active_content_and_external_targets_are_counted(book):
    with zipfile.ZipFile(book) as z:
        rels = (
            z.read("xl/worksheets/_rels/sheet1.xml.rels").decode()
            if "xl/worksheets/_rels/sheet1.xml.rels" in z.namelist()
            else None
        )
    ext = '<Relationship Id="rX" Type="t" Target="https://example.invalid/" TargetMode="External"/>'
    rels = (
        rels or '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
    )
    rels = rels.replace("</Relationships>", ext + "</Relationships>")
    synth.rewrite(
        book,
        {"xl/worksheets/_rels/sheet1.xml.rels": None},
        add={
            "xl/worksheets/_rels/sheet1.xml.rels": rels.encode(),
            "xl/connections.xml": b"<connections/>",
            "xl/embeddings/oleObject1.bin": b"\0",
            "xl/activeX/activeX1.xml": b"<ax/>",
        },
    )
    a = inspect(book)["archive"]
    assert a["active_content_parts"] == 3
    assert a["external_targets"] == 1


def test_a_text_cell_that_starts_with_equals_is_not_a_formula(tmp_path):
    wb = Workbook()
    wb.active["A1"] = "=not a formula"
    wb.active["A1"].data_type = "s"
    s = inspect(synth.save(wb, tmp_path / "f.xlsx"))["sheets"][0]
    assert s["formulas"] == 0 and s["formulas_uncached"] == 0


def test_a_literal_percent_sign_in_a_format_is_not_percent_scaling(tmp_path):
    wb = Workbook()
    for ref, fmt in (("A1", '0.0"%"'), ("A2", "0.0\\%"), ("A3", "0.0%")):
        wb.active[ref] = 2.5
        wb.active[ref].number_format = fmt
    s = inspect(synth.save(wb, tmp_path / "f.xlsx"))["sheets"][0]
    assert s["percent_format"] == 1
    assert s["literal_percent_format"] == 2


def test_a_merged_period_header_and_its_span_are_reported(tmp_path):
    wb = Workbook()
    wb.active["B1"] = "2026"
    wb.active.merge_cells("B1:E1")
    s = inspect(synth.save(wb, tmp_path / "f.xlsx"))["sheets"][0]
    assert s["merged_period_headers"] == 1 and s["merged_period_header_cols"] == 4


def test_workbook_counts_worksheets_and_chartsheets_separately(book):
    w = inspect(book)["workbook"]
    assert w["sheets"] == 3 and w["chartsheets"] == 0


def test_an_encrypted_member_is_refused(book, monkeypatch):
    import xlsxinspect.inspect as mod

    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("must not open"))
    raw = bytearray(book.read_bytes())
    at = raw.index(b"PK\x01\x02")  # first central-directory entry; general-purpose flag at offset 8
    raw[at + 8] |= 1
    book.write_bytes(bytes(raw))
    r = inspect(book)
    assert r["status"] == "refused" and r["archive"]["encrypted"] is True


def test_a_compression_ratio_over_the_limit_is_refused(book, monkeypatch):
    import xlsxinspect.inspect as mod

    monkeypatch.setattr(mod, "MAX_RATIO", 1)
    r = inspect(book)
    assert r["status"] == "refused" and r["archive"]["over_limit"] is True


def test_shared_formulas_count_every_cell_that_uses_them(tmp_path):
    wb = Workbook()
    for ref in ("A1", "A2", "A3"):
        wb.active[ref] = 1
    wb.active["B1"] = "=A1+1"
    path = synth.save(wb, tmp_path / "f.xlsx")
    xml = synth.sheet1(path).decode()
    xml = xml.replace("<f>A1+1</f>", '<f t="shared" ref="B1:B3" si="0">A1+1</f>')
    xml = xml.replace(
        '<c r="A2" t="n"><v>1</v></c>', '<c r="A2" t="n"><v>1</v></c><c r="B2"><f t="shared" si="0"/></c>'
    )
    xml = xml.replace(
        '<c r="A3" t="n"><v>1</v></c>', '<c r="A3" t="n"><v>1</v></c><c r="B3"><f t="shared" si="0"/></c>'
    )
    assert xml.count('si="0"') == 3, "fixture XML shape changed"
    synth.rewrite(path, {"xl/worksheets/sheet1.xml": xml.encode()})
    s = inspect(path)["sheets"][0]
    assert (s["formulas"], s["formulas_uncached"]) == (3, 3)

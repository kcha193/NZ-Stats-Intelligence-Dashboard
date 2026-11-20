"""Synthetic security regressions for PR 67. No bank files or contents are used."""

import zipfile

import pytest
from openpyxl import Workbook

from tests import synth
from xlsxinspect.guard import emit
from xlsxinspect.inspect import inspect

SHEET = "xl/worksheets/sheet1.xml"
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"


@pytest.fixture
def book(tmp_path):
    return synth.save(synth.forecast_book(), tmp_path / "synthetic.xlsx")


@pytest.mark.parametrize(
    "fragment",
    [
        '<dimension ref="A1:XFD1048576"/>',
        '<sheetData><row r="1048576"><c r="XFD1048576" t="n"><v>1</v></c></row></sheetData>',
        '<sheetData><row r="1048576"><c t="n"><v>1</v></c></row></sheetData>',
        '<mergeCells><mergeCell ref="A1:XFD1048576"/></mergeCells>',
    ],
    ids=["dimension", "sparse-corner", "implicit-cell", "merged-range"],
)
def test_expansion_is_refused_before_openpyxl(book, fragment, monkeypatch):
    import xlsxinspect.inspect as mod

    xml = f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{fragment}</worksheet>'
    synth.rewrite(book, {SHEET: xml.encode()})

    def must_not_load(*args, **kwargs):
        pytest.fail("unsafe expansion reached openpyxl")

    monkeypatch.setattr(mod, "load_workbook", must_not_load)
    result = inspect(book)
    assert result["status"] == "refused"
    assert result["archive"]["over_limit"] is True
    emit(result)


def test_valid_sparse_cells_and_merged_headers_keep_counts(tmp_path):
    wb = Workbook()
    wb.active["A1"] = "2026"
    wb.active.merge_cells("A1:D1")
    wb.active["Z100"] = "=1+1"
    result = inspect(synth.save(wb, tmp_path / "sparse.xlsx"))
    assert result["status"] == "ok"
    sheet = result["sheets"][0]
    assert (sheet["rows"], sheet["cols"]) == (100, 26)
    assert (sheet["formulas"], sheet["formulas_uncached"], sheet["merged_period_header_cols"]) == (1, 1, 4)
    emit(result)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-16-le", "utf-16-be"])
@pytest.mark.parametrize("escaped", [False, True])
def test_metadata_is_encoding_aware(book, encoding, escaped):
    mode = "Ext&#101;rnal" if escaped else "External"
    macro = "macro&#69;nabled" if escaped else "macroEnabled"
    declaration = f'<?xml version="1.0" encoding="{"UTF-8" if encoding == "utf-8" else "UTF-16"}"?>'
    rels = f'{declaration}<Relationships xmlns="{RELS}"><Relationship Id="x" Type="t" Target="https://example.invalid/" TargetMode="{mode}"/></Relationships>'
    with zipfile.ZipFile(book) as z:
        types = z.read("[Content_Types].xml").decode()
    types = declaration + types.replace(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        f"application/vnd.ms-excel.sheet.{macro}.main+xml",
    )
    synth.rewrite(book, {"[Content_Types].xml": types.encode(encoding)}, add={"custom.rels": rels.encode(encoding)})
    archive = inspect(book)["archive"]
    assert archive["unreadable"] is False
    assert archive["external_targets"] == 1
    assert archive["macro_content_type"] is True


@pytest.mark.parametrize(
    "name,data",
    [
        ("custom.rels", b'<Relationships><Relationship TargetMode="External"/>'),
        ("custom.rels", b'<?xml version="1.0" encoding="unsupported"?><Relationships/>'),
        ("[Content_Types].xml", b'<Types><Override ContentType="macroEnabled"/>'),
        ("custom.rels", b"<wrong/>"),
    ],
    ids=["broken-rels", "unsupported-encoding", "broken-types", "wrong-root"],
)
def test_uninspectable_metadata_fails_closed(book, name, data, monkeypatch):
    import xlsxinspect.inspect as mod

    synth.rewrite(
        book,
        {name: data} if name == "[Content_Types].xml" else {},
        add={} if name == "[Content_Types].xml" else {name: data},
    )
    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("uninspectable metadata reached loader"))
    result = inspect(book)
    assert result["status"] == "refused"
    assert result["archive"]["unreadable"] is True
    assert result["archive"]["external_targets"] is None
    assert result["archive"]["macro_content_type"] is None
    emit(result)


@pytest.mark.parametrize(
    "fragment",
    [
        '<hyperlinks><hyperlink ref="A1:XFD1048576" location="A1"/></hyperlinks>',
        '<hyperlinks><hyperlink ref="XFD1048576" location="A1"/></hyperlinks>',
    ],
)
def test_hyperlink_allocation_is_bounded_before_loading(book, fragment, monkeypatch):
    import xlsxinspect.inspect as mod

    xml = synth.sheet1(book).decode().replace("</worksheet>", fragment + "</worksheet>")
    synth.rewrite(book, {SHEET: xml.encode()})
    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("unbounded hyperlink reached loader"))
    result = inspect(book)
    assert result["status"] == "refused" and result["archive"]["over_limit"] is True


def test_comment_range_cannot_expand_during_loading(book, monkeypatch):
    import xlsxinspect.inspect as mod

    with zipfile.ZipFile(book) as z:
        name = "xl/comments/comment1.xml"
        xml = z.read(name).replace(b'ref="B4"', b'ref="A1:XFD1048576"')
    synth.rewrite(book, {name: xml})
    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("unbounded comment reached loader"))
    result = inspect(book)
    assert result["status"] == "refused" and result["archive"]["over_limit"] is True


@pytest.mark.parametrize(
    "limit", ["MAX_WORKBOOK_CELLS", "MAX_MERGED_CELLS", "MAX_MERGES", "MAX_XML_ELEMENTS", "MAX_XML_DEPTH"]
)
def test_cumulative_and_parser_limits_refuse_before_loading(book, monkeypatch, limit):
    import xlsxinspect.inspect as mod

    monkeypatch.setattr(mod, limit, 0 if limit == "MAX_MERGES" else 1)
    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("over-budget archive reached loader"))
    result = inspect(book)
    assert result["status"] == "refused" and result["archive"]["over_limit"] is True
    emit(result)


def test_missing_content_types_is_unknown_and_refused(book):
    synth.rewrite(book, {"[Content_Types].xml": None})
    result = inspect(book)
    assert result["status"] == "refused" and result["archive"]["unreadable"] is True
    assert result["archive"]["macro_content_type"] is None


@pytest.mark.parametrize(
    "xml",
    [
        '<document><mergeCells><mergeCell ref="A1:XFD1048576"/></mergeCells></document>',
        '<worksheet><sheetData><row r="1"><bogus r="XFD1048576"><v>1</v></bogus></row></sheetData></worksheet>',
        '<worksheet><sheetData><row r="100"><row r="1"><c r="A1"><v>1</v></c></row><c><v>1</v></c></row></sheetData></worksheet>',
    ],
    ids=["unexpected-root", "non-cell-row-child", "nested-rows"],
)
def test_loader_parser_discrepancies_fail_closed(book, xml, monkeypatch):
    import xlsxinspect.inspect as mod

    xml = xml.replace("><", ' xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><', 1)
    synth.rewrite(book, {SHEET: xml.encode()})
    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("ambiguous worksheet reached loader"))
    result = inspect(book)
    assert result["status"] == "refused"
    assert result["archive"]["unreadable"] is True
    emit(result)


@pytest.mark.parametrize("limit", ["MAX_WORKBOOK_CELLS", "MAX_MERGED_CELLS", "MAX_MERGES"])
def test_workbook_budgets_are_cumulative_across_sheets(tmp_path, monkeypatch, limit):
    import xlsxinspect.inspect as mod

    wb = Workbook()
    wb.active.merge_cells("A1:C1")
    wb.create_sheet().merge_cells("A1:C1")
    path = synth.save(wb, tmp_path / "cumulative.xlsx")
    # Each sheet fits alone (3 cells, one merge); together they exceed this budget.
    monkeypatch.setattr(mod, limit, 1 if limit == "MAX_MERGES" else 5)
    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("cumulative expansion reached loader"))
    result = inspect(path)
    assert result["status"] == "refused" and result["archive"]["over_limit"] is True


@pytest.mark.parametrize("distinct_id", [False, True])
def test_repeated_worksheet_targets_fail_closed(book, monkeypatch, distinct_id):
    import xlsxinspect.inspect as mod

    with zipfile.ZipFile(book) as z:
        workbook = z.read("xl/workbook.xml").decode()
        rels = z.read("xl/_rels/workbook.xml.rels").decode()
    alias_id = "alias" if distinct_id else "rId1"
    alias = f'<sheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" name="Alias" sheetId="4" r:id="{alias_id}"/>'
    workbook = workbook.replace("</sheets>", alias + "</sheets>")
    if distinct_id:
        target = '<Relationship Id="alias" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/../worksheets/sheet1.xml"/>'
        rels = rels.replace("</Relationships>", target + "</Relationships>")
    synth.rewrite(book, {"xl/workbook.xml": workbook.encode(), "xl/_rels/workbook.xml.rels": rels.encode()})
    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("aliased worksheet reached loader"))
    result = inspect(book)
    assert result["status"] == "refused" and result["archive"]["unreadable"] is True


@pytest.mark.parametrize(
    "part,container,child",
    [
        (SHEET, "mergeCells", '<x ref="A1:XFD1048576"/>'),
        (SHEET, "hyperlinks", '<x ref="A1:XFD1048576" location="A1"/>'),
        (
            "xl/comments/comment1.xml",
            "commentList",
            '<x ref="A1:XFD1048576" authorId="0"><text><t>synthetic</t></text></x>',
        ),
    ],
)
def test_loader_sequence_children_must_match_their_schema(book, monkeypatch, part, container, child):
    import xlsxinspect.inspect as mod

    root = "comments" if container == "commentList" else "worksheet"
    authors = "<authors><author>synthetic</author></authors>" if root == "comments" else ""
    xml = f'<{root} xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{authors}<{container}>{child}</{container}></{root}>'
    synth.rewrite(book, {part: xml.encode()})
    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("ambiguous sequence reached loader"))
    result = inspect(book)
    assert result["status"] == "refused" and result["archive"]["unreadable"] is True


@pytest.mark.parametrize(
    "content_type", ["application/vnd.ms-excel.macrosheet+xml", "application/vnd.ms-excel.intlmacrosheet+xml"]
)
def test_legacy_macro_content_types_are_not_reported_absent(book, content_type):
    with zipfile.ZipFile(book) as z:
        types = z.read("[Content_Types].xml").decode()
    extra = f'<Override PartName="/xl/macrosheets/sheet.xml" ContentType="{content_type}"/>'
    synth.rewrite(book, {"[Content_Types].xml": types.replace("</Types>", extra + "</Types>").encode()})
    assert inspect(book)["archive"]["macro_content_type"] is True


def test_valid_workbook_with_a_positioned_chart_remains_inspectable(tmp_path):
    from openpyxl.chart import BarChart, Reference

    wb = Workbook()
    for value in (1, 2, 3):
        wb.active.append([value])
    chart = BarChart()
    chart.add_data(Reference(wb.active, min_col=1, min_row=1, max_row=3))
    wb.active.add_chart(chart, "D2")
    result = inspect(synth.save(wb, tmp_path / "chart.xlsx"))
    assert result["status"] == "ok"
    assert result["sheets"][0]["numeric"] == 3
    emit(result)


def test_shared_non_worksheet_package_dependencies_are_allowed(book):
    relationship = f'<Relationships xmlns="{RELS}"><Relationship Id="x" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="/xl/media/shared.png"/></Relationships>'
    synth.rewrite(
        book,
        {},
        add={
            "xl/drawings/_rels/first.xml.rels": relationship.encode(),
            "xl/drawings/_rels/second.xml.rels": relationship.encode(),
            "xl/media/shared.png": b"synthetic image placeholder; not loaded",
        },
    )
    assert inspect(book)["status"] == "ok"


def test_sheet_aliases_cannot_hide_behind_an_unexpected_relationship_type(book, monkeypatch):
    import xlsxinspect.inspect as mod

    with zipfile.ZipFile(book) as z:
        workbook = z.read("xl/workbook.xml").decode()
        rels = z.read("xl/_rels/workbook.xml.rels").decode()
    alias = '<sheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" name="Alias" sheetId="4" r:id="alias"/>'
    target = '<Relationship Id="alias" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="/xl/worksheets/sheet1.xml"/>'
    synth.rewrite(
        book,
        {
            "xl/workbook.xml": workbook.replace("</sheets>", alias + "</sheets>").encode(),
            "xl/_rels/workbook.xml.rels": rels.replace("</Relationships>", target + "</Relationships>").encode(),
        },
    )
    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("disguised sheet alias reached loader"))
    result = inspect(book)
    assert result["status"] == "refused" and result["archive"]["unreadable"] is True


def test_missing_referenced_worksheet_fails_closed(book, monkeypatch):
    import xlsxinspect.inspect as mod

    synth.rewrite(book, {SHEET: None})
    monkeypatch.setattr(mod, "load_workbook", lambda *a, **k: pytest.fail("missing worksheet reached loader"))
    result = inspect(book)
    assert result["status"] == "refused" and result["archive"]["unreadable"] is True
    assert result["archive"]["external_targets"] is None
    emit(result)

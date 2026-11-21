"""The bounded stdlib XLSX cell reader (Phase 4AP). Synthetic workbooks only."""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from nzstats.domain import IngestError
from nzstats.research import xlsx_cells
from nzstats.research.xlsx_cells import XCell, cells_sha256, read_cells, render_text, serial_date

from .xlsx_support import MACRO_CT, C, Sheet, build

FIXED_TEXTS = {
    "workbook too large",
    "workbook archive refused",
    "workbook content refused",
    "workbook cannot be read",
    "workbook over cell budget",
}


def sample() -> bytes:
    return build(
        [
            Sheet("Fictional cover"),
            Sheet(
                "Fictional data",
                {
                    (1, 2): C("Fictional growth"),
                    (2, 2): C("% q/q", kind="inline"),
                    (3, 1): C(date(2026, 3, 1), fmt=14),
                    (4, 1): C(date(2026, 6, 1), fmt="d/mm/yyyy"),
                    (3, 2): C(1.5, fmt="0.0"),
                    (4, 2): C("2.0999999999999996", kind="number", fmt="0.0", bold=True),
                    (5, 2): C(True),
                    (6, 2): C("#N/A", kind="error"),
                    (7, 2): C(4.0, kind="formula"),
                },
                merges=("B1:E1",),
            ),
            Sheet("Fictional hidden", {(1, 1): C(1)}, state="hidden"),
            Sheet("Fictional very hidden", {(1, 1): C(1)}, state="veryHidden"),
        ],
        drawing_paragraphs=(("Fictional ", "Bank"), ("Second paragraph",)),
    )


def read(body: bytes) -> xlsx_cells.WorkbookCells:
    return read_cells(body, isolate=False)


def refused(body: bytes) -> str:
    with pytest.raises(IngestError) as caught:
        read(body)
    message = str(caught.value)
    assert message in FIXED_TEXTS
    return message


def test_reads_cells_types_styles_and_formats():
    wb = read(sample())
    assert [(s.position, s.name, s.state) for s in wb.sheets] == [
        (1, "Fictional cover", "visible"),
        (2, "Fictional data", "visible"),
        (3, "Fictional hidden", "hidden"),
        (4, "Fictional very hidden", "very_hidden"),
    ]
    cells = wb.sheets[1].cells
    assert cells[(1, 2)] == XCell(1, 2, "text", "Fictional growth", False, "General", False)
    assert cells[(2, 2)].kind == "text" and cells[(2, 2)].text == "% q/q"
    assert cells[(3, 1)].is_date and cells[(3, 1)].number_format == "mm-dd-yy"
    assert cells[(4, 1)].is_date and cells[(4, 1)].number_format == "d/mm/yyyy"
    assert cells[(3, 2)] == XCell(3, 2, "number", "1.5", False, "0.0", False)
    assert cells[(4, 2)] == XCell(4, 2, "number", "2.0999999999999996", True, "0.0", False)
    assert (cells[(5, 2)].kind, cells[(5, 2)].text) == ("bool", "1")
    assert (cells[(6, 2)].kind, cells[(6, 2)].text) == ("error", "#N/A")
    assert wb.sheets[1].merges == ((1, 2, 1, 5),)
    assert wb.sheets[0].cells == {}
    assert wb.drawing_texts == ("Fictional Bank", "Second paragraph")
    assert wb.date1904 is False


def test_a_formula_is_read_as_a_formula_and_never_evaluated():
    cell = read(sample()).sheets[1].cells[(7, 2)]
    assert cell.kind == "formula" and cell.text == "4.0"  # the cached value, kept as text only


def test_date1904_and_serial_dates():
    wb = read(build([Sheet("S", {(1, 1): C(date(2026, 3, 1), fmt=14)})], date1904=True))
    assert wb.date1904 is True
    assert serial_date(wb.sheets[0].cells[(1, 1)].text, True) == date(2026, 3, 1)
    assert serial_date("46082", False) == date(2026, 3, 1)
    assert serial_date("46082.5", False) is None  # a time of day is not a date
    assert serial_date("abc", False) is None
    assert serial_date("-1", False) is None
    assert serial_date("30", False) is None  # before 1 March 1900, where the 1900 system is wrong


def test_number_formats_that_are_not_dates():
    wb = read(
        build(
            [
                Sheet(
                    "S",
                    {(1, 1): C(1.25, fmt="0.00"), (1, 2): C(3, fmt='0.0"%"'), (1, 3): C(2, fmt=0)},
                )
            ]
        )
    )
    cells = wb.sheets[0].cells
    assert [
        (c.number_format, c.is_date) for c in (cells[(1, 1)], cells[(1, 2)], cells[(1, 3)])
    ] == [
        ("0.00", False),
        ('0.0"%"', False),
        ("General", False),
    ]


def test_render_text_is_sheet_then_rows():
    text = render_text(read(sample()))
    lines = text.splitlines()
    assert lines[0] == "Fictional cover"
    assert lines[1] == "Fictional data"
    assert lines[2] == "Fictional growth"
    assert "% q/q" in lines and "46082\t1.5" in lines


def test_cells_sha256_is_stable_and_content_sensitive():
    a, b = read(sample()), read(sample())
    assert cells_sha256(a) == cells_sha256(b) and len(cells_sha256(a)) == 64
    other = read(build([Sheet("Fictional data", {(1, 1): C(1.6, fmt="0.0")})]))
    assert cells_sha256(other) != cells_sha256(a)


def test_isolated_and_in_process_results_are_equal():
    body = sample()
    assert read_cells(body, isolate=True) == read_cells(body, isolate=False)


def test_isolated_refusals_keep_their_fixed_text():
    with pytest.raises(IngestError, match="^workbook archive refused$"):
        read_cells(b"not a zip at all", isolate=True)


def _zip(members: dict[str, bytes], *, flag_encrypted: str | None = None) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(zipfile.ZipInfo(name), data)
    body = bytearray(out.getvalue())
    if (
        flag_encrypted is not None
    ):  # zipfile resets flag bits on write: set "encrypted" in the central directory
        name = flag_encrypted.encode()
        at = body.find(b"PK\x01\x02")
        while at >= 0:
            length = int.from_bytes(body[at + 28 : at + 30], "little")
            if bytes(body[at + 46 : at + 46 + length]) == name:
                body[at + 8] |= 1
                break
            at = body.find(b"PK\x01\x02", at + 4)
        else:
            raise AssertionError("member not found")
    return bytes(body)


def _members(body: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_refuses_what_is_not_a_zip():
    assert refused(b"PK\x03\x04 broken") == "workbook archive refused"


def test_refuses_an_oversized_archive(monkeypatch):
    monkeypatch.setattr(xlsx_cells, "MAX_ARCHIVE", 100)
    assert refused(sample()) == "workbook too large"


@pytest.mark.parametrize(
    ("name", "value"), [("MAX_MEMBERS", 3), ("MAX_UNPACKED", 500), ("MAX_RATIO", 1)]
)
def test_refuses_archives_over_member_limits(monkeypatch, name, value):
    monkeypatch.setattr(xlsx_cells, name, value)
    assert refused(sample()) == "workbook archive refused"


def test_refuses_over_the_cell_budget(monkeypatch):
    monkeypatch.setattr(xlsx_cells, "MAX_CELLS", 5)
    assert refused(sample()) == "workbook over cell budget"


def test_refuses_an_encrypted_member():
    members = _members(sample())
    assert refused(_zip(members, flag_encrypted="xl/styles.xml")) == "workbook archive refused"


@pytest.mark.parametrize("name", ["../evil.xml", "/abs.xml", "xl\\worksheets\\x.xml"])
def test_refuses_unsafe_paths(name):
    members = _members(sample()) | {name: b"<x/>"}
    assert refused(_zip(members)) == "workbook archive refused"


@pytest.mark.parametrize(
    "name",
    [
        "xl/vbaProject.bin",
        "xl/externalLinks/externalLink1.xml",
        "xl/activeX/activeX1.xml",
        "xl/embeddings/oleObject1.bin",
        "xl/connections.xml",
        "customUI/customUI.xml",
    ],
)
def test_refuses_active_or_external_content(name):
    assert (
        refused(build([Sheet("S", {(1, 1): C(1)})], extra={name: b"<x/>"}))
        == "workbook content refused"
    )


def test_refuses_a_macro_content_type():
    assert (
        refused(build([Sheet("S", {(1, 1): C(1)})], content_type=MACRO_CT))
        == "workbook content refused"
    )


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16-le", "utf-16-be"])
@pytest.mark.parametrize("marker", ["<!DOCTYPE x>", '<!ENTITY e "x">'])
def test_refuses_xml_declarations_in_any_member(encoding, marker):
    bom = {"utf-8": b"", "utf-16-le": b"\xff\xfe", "utf-16-be": b"\xfe\xff"}[encoding]
    doc = bom + f'<?xml version="1.0"?>{marker}<x/>'.encode(encoding)
    assert refused(build([Sheet("S", {(1, 1): C(1)})], extra={"docProps/custom.xml": doc})) == (
        "workbook content refused"
    )


def test_refuses_a_missing_sheet_target():
    assert refused(build([Sheet("S", {(1, 1): C(1)})], drop=("xl/worksheets/sheet1.xml",))) == (
        "workbook cannot be read"
    )


def test_refuses_an_external_sheet_relationship():
    body = build([Sheet("S", {(1, 1): C(1)})])
    members = _members(body)
    members["xl/_rels/workbook.xml.rels"] = members["xl/_rels/workbook.xml.rels"].replace(
        b'Target="worksheets/sheet1.xml"',
        b'Target="https://example.org/s.xml" TargetMode="External"',
    )
    assert refused(_zip(members)) == "workbook cannot be read"


def test_refuses_malformed_xml_and_excessive_depth():
    members = _members(sample())
    broken = dict(members, **{"xl/styles.xml": b"<styleSheet><unclosed>"})
    assert refused(_zip(broken)) == "workbook cannot be read"
    deep = dict(members, **{"docProps/app.xml": b"<a>" * 200 + b"</a>" * 200})
    assert refused(_zip(deep)) == "workbook cannot be read"


def test_errors_never_carry_workbook_text(caplog):
    members = _members(sample())
    members["xl/styles.xml"] = b"<styleSheet>SECRET-FICTIONAL-TEXT<unclosed>"
    with pytest.raises(IngestError) as caught:
        read(_zip(members))
    assert "SECRET" not in str(caught.value) and "SECRET" not in caplog.text
    assert caught.value.__cause__ is None or "SECRET" not in repr(caught.value.__cause__)

"""The owner's series review of the forecasts workbook (Phase 4AQ): structure, never values, real terminal only.
Fictional workbooks from the Phase 4AP mapping tests; every figure is invented."""

from __future__ import annotations

import re
from types import SimpleNamespace

from nzstats.cli import main
from nzstats.research.xlsx_cells import read_cells
from nzstats.research.xlsx_review import review_lines

from .test_xlsx_anz import (
    AS_AT,
    CPI_AA,
    GDP_AA,
    GDP_QQ,
    LEGEND,
    PUBLISHER,
    QUARTERS,
    SHA,
    TITLE,
    UNEMP,
    data_sheet,
    run,
    series,
    standard,
)
from .test_xlsx_pipeline import WORKBOOK_URL, env, no_network, workbook  # noqa: F401
from .xlsx_support import C, Sheet, build


def review(sheets) -> str:
    wb = read_cells(build(sheets, drawing_paragraphs=(("Fictional Bank",),)), isolate=False)
    lines = review_lines(wb, publisher_names=PUBLISHER, document_title=TITLE, workbook_sha256=SHA)
    return "\n".join(lines)


def test_the_review_names_each_sheet_block_column_and_note():
    out = review(standard())
    assert f"workbook sha256 {SHA}" in out
    assert 'sheet 2 "Growth": quarterly 2025-03-01 to 2026-12-01 (8 dates)' in out
    assert f'legend: "{LEGEND}"' in out and f'as at: "{AS_AT}"' in out
    assert 'block 1 "GDP" (columns B to C)' in out
    assert 'column B unit "% q/q": indicator gdp' in out
    assert "forecast boundary 2026-06-01 to 2026-12-01 (3 bold)" in out
    assert 'sheet 3 "Prices"' in out and 'block 2 "Unemployment rate"' in out


def test_the_review_shows_each_columns_result_from_the_current_interpreter():
    out = review(standard())
    b = next(line for line in out.splitlines() if "column B " in line and "% q/q" in line)
    assert b.endswith("result 3 candidates")
    two_gdp = standard(
        growth=[
            ("GDP", [("% q/q", series([0.5] * 8))]),
            ("Nominal GDP", [("% q/q", series([0.2] * 8))]),
        ]
    )
    out = review(two_gdp)
    assert out.count("result ambiguous_indicator") == 2


def test_the_review_shows_an_untitled_data_column_rejected_by_the_interpreter():
    baseline_forecasts, baseline_rejections = run(standard())
    assert len(baseline_forecasts) == 12 and baseline_rejections == ()

    sheets = standard()
    sheets[1].cells[(8, 4)] = C(17.25, bold=True)
    forecasts, rejections = run(sheets)
    assert forecasts == baseline_forecasts
    assert [(r.page, r.col, r.code) for r in rejections] == [(2, 4, "unmapped_row")]

    assert "  column D: no block title (unmapped_row)" in review(sheets).splitlines()


def test_the_review_lists_each_data_column_once_at_title_boundaries():
    sheets = standard()
    growth = sheets[1]
    growth.cells[(8, 4)] = C(17.25, bold=True)  # immediately after the B:C title merge
    growth.cells[(2, 5)] = C("Fictional unit \u009b2J")
    growth.cells[(8, 5)] = C(18.25, bold=True)
    growth.cells[(1, 6)] = C("Other series")
    growth.cells[(8, 6)] = C(19.25, bold=True)
    growth.merges += ("G1:H1",)  # a blank title merge already reported by _blocks
    growth.cells[(8, 8)] = C(20.25, bold=True)
    growth.cells[(2, 9)] = C("Header only")
    growth.cells[(11, 10)] = C(21.25)  # metadata after the recognised dates

    out = review(sheets)
    growth_out = out.split('sheet 2 "Growth"', 1)[1].split('sheet 3 "Prices"', 1)[0]
    columns = re.findall(r"^ +column ([A-Z]+)[ :]", growth_out, re.MULTILINE)
    unmapped = re.findall(
        r"^  column ([A-Z]+): no block title \(unmapped_row\)$", growth_out, re.MULTILINE
    )
    assert columns == ["B", "C", "F", "D", "E", "H"]
    assert unmapped == ["D", "E", "H"]
    assert 'block 1 "GDP" (columns B to C)' in growth_out
    assert 'block 2 "Other series" (columns F to F)' in growth_out
    assert not re.search(r"\d\.\d", growth_out)
    assert "\u009b" not in growth_out


def test_the_review_never_prints_a_cell_value():
    out = review(standard())
    for value in (*GDP_QQ, *GDP_AA, *CPI_AA, *UNEMP):
        assert not re.search(rf"(?<![\d.]){re.escape(str(value))}(?![\d.])", out), value
    # Structure (dates, hashes, counts, codes) never needs a decimal, so any decimal is a leaked value.
    assert not re.search(r"\d\.\d", out)


def test_a_sheet_the_interpreter_cannot_read_still_lists_its_blocks():
    monthly = data_sheet(
        "Rates", [("Official cash rate", [("% p.a.", series([3.0] * 8))])], dates=QUARTERS
    )
    monthly.cells[(4, 1)] = C(QUARTERS[0].replace(month=4), fmt="d/mm/yyyy")
    monthly.cells[(8, 3)] = C(17.25, bold=True)
    monthly.merges += ("D1:E1",)
    monthly.cells[(8, 5)] = C(18.25, bold=True)
    out = review(standard(extra=[monthly]))
    assert 'sheet 4 "Rates": unsupported_period' in out
    assert 'block 1 "Official cash rate"' in out and 'column B unit "% p.a."' in out
    rates_out = out.split('sheet 4 "Rates"', 1)[1]
    assert "column C" not in rates_out
    assert "column E: no block title (unmapped_row)" in rates_out


def test_control_characters_in_workbook_text_are_escaped():
    # ESC is not legal XML (the reader refuses it); the C1 control sequence introducer is, and a terminal obeys it.
    sheets = standard(growth=[("GDP\u009b2J", [("% q/q", series([0.5] * 8))])])
    out = review(sheets)
    assert "\u009b" not in out and "\\u009b" in out


def test_empty_and_hidden_sheets_are_listed_without_columns():
    hidden = data_sheet(
        "Hidden fixture", [("Hidden title", [("% q/q", series(GDP_QQ))])], state="veryHidden"
    )
    hidden.cells[(8, 3)] = C(17.25, bold=True)
    out = review([Sheet("Cover"), hidden])
    assert out.splitlines() == [
        f"workbook sha256 {SHA}",
        'sheet 1 "Cover": no cells',
        'sheet 2 "Hidden fixture": hidden_sheet (very_hidden)',
    ]


# ---------------------------------------------------------------- command line


def _imported(env, tmp_path, monkeypatch) -> int:  # noqa: F811
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(env.settings.data_dir))
    path = tmp_path / "Fictional-forecasts.xlsx"
    path.write_bytes(workbook())
    args = ["research", "import", "anz", str(path), "--url", WORKBOOK_URL, "--importer", "Owner", "--note", "n",
            "--title", "ANZ Forecasts", "--published-on", "2026-11-05"]  # fmt: skip
    assert main(args) == 0
    return 1


def test_the_review_command_refuses_outside_a_real_terminal(env, tmp_path, monkeypatch, capsys):  # noqa: F811
    v = _imported(env, tmp_path, monkeypatch)
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: False))
    assert main(["research", "tables", "review", str(v)]) == 2
    out = capsys.readouterr().out
    assert "real terminal" in out and "Growth" not in out and "GDP" not in out


def test_the_review_command_prints_the_structure_in_a_terminal(env, tmp_path, monkeypatch, capsys):  # noqa: F811
    v = _imported(env, tmp_path, monkeypatch)
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("nzstats.research.cli._stdout_is_terminal", lambda: True)
    assert main(["research", "tables", "review", str(v)]) == 0
    out = capsys.readouterr().out
    assert 'sheet 2 "Growth"' in out and "Nothing was requested; no model was used." in out


def test_the_review_command_refuses_a_version_that_is_not_a_workbook(env, monkeypatch, capsys):  # noqa: F811
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(env.settings.data_dir))
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("nzstats.research.cli._stdout_is_terminal", lambda: True)
    assert main(["research", "tables", "review", "99"]) == 1
    assert "refused (unknown version)" in capsys.readouterr().out

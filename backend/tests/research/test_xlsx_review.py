"""The owner's series review of the forecasts workbook (Phase 4AQ): structure, never values, real terminal only.
Fictional workbooks from the Phase 4AP mapping tests; every figure is invented."""

from __future__ import annotations

from types import SimpleNamespace

from nzstats.cli import main
from nzstats.research.xlsx_cells import read_cells
from nzstats.research.xlsx_review import review_lines

from .test_xlsx_anz import (
    AS_AT,
    LEGEND,
    PUBLISHER,
    QUARTERS,
    SHA,
    TITLE,
    data_sheet,
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


def test_the_review_never_prints_a_cell_value():
    out = review(standard())
    for value in ("0.5", "0.7", "2.9", "4.8", "1.6"):
        assert value not in out


def test_a_sheet_the_interpreter_cannot_read_still_lists_its_blocks():
    monthly = data_sheet(
        "Rates", [("Official cash rate", [("% p.a.", series([3.0] * 8))])], dates=QUARTERS
    )
    monthly.cells[(4, 1)] = C(QUARTERS[0].replace(month=4), fmt="d/mm/yyyy")
    out = review(standard(extra=[monthly]))
    assert 'sheet 4 "Rates": unsupported_period' in out
    assert 'block 1 "Official cash rate"' in out and 'column B unit "% p.a."' in out


def test_control_characters_in_workbook_text_are_escaped():
    # ESC is not legal XML (the reader refuses it); the C1 control sequence introducer is, and a terminal obeys it.
    sheets = standard(growth=[("GDP\u009b2J", [("% q/q", series([0.5] * 8))])])
    out = review(sheets)
    assert "\u009b" not in out and "\\u009b" in out


def test_a_cover_sheet_is_listed_without_blocks():
    out = review([Sheet("Cover"), *standard()[1:]])
    assert 'sheet 1 "Cover": no cells' in out


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

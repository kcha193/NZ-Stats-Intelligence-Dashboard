"""The synthetic run gives one row per (case, parser) and records a parser failure as a row, not an exception."""

from pdfbench.run_synthetic import markdown, rows
from pdfbench.synth import cases


def test_one_row_per_case_and_parser():
    picked = [c for c in cases() if c.name in {"ruled_control", "p8_stacked"}]
    out = rows(picked, ["existing", "plumber_default"])
    assert [(r["case"], r["parser"]) for r in out] == [
        ("p8_stacked", "existing"),
        ("p8_stacked", "plumber_default"),
        ("ruled_control", "existing"),
        ("ruled_control", "plumber_default"),
    ]
    assert all(r["error"] in (None, "error", "timeout") for r in out)
    assert all(isinstance(r["values_aligned"], int) for r in out)


def test_markdown_has_a_header_and_a_line_per_row():
    picked = [c for c in cases() if c.name == "ruled_control"]
    text = markdown(rows(picked, ["existing"]))
    lines = text.strip().splitlines()
    assert lines[0].startswith("| case | parser |") and len(lines) == 3

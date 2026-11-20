"""Synthetic PDFs (SYNTHETIC FIXTURE text only) that replicate the layout facts recorded for ANZ version 4 in
docs/phase-4ak-anz-pdf-compat.md, plus control cases. Drawn with reportlab, as the PDF skill recommends. No real report
text or figure is used: labels, values and notes are invented.
"""

from __future__ import annotations

import io

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from pdfbench.model import BBox, Case, Item, Line, TruthTable

FONT = "Helvetica"
SIZE = 8.5  # table text size recorded for page 5
SMALL = 5.0  # small footnote digit recorded for page 5
LEAD = 13.0  # body row pitch


class _Page:
    def __init__(self) -> None:
        self.items: list[Item] = []
        self.lines: list[Line] = []

    def text(self, x: float, y: float, s: str, size: float = SIZE) -> tuple[float, float]:
        self.items.append((x, y, size, s))
        return x, x + stringWidth(s, FONT, size)

    def right(self, x1: float, y: float, s: str, size: float = SIZE) -> tuple[float, float]:
        return self.text(x1 - stringWidth(s, FONT, size), y, s, size)

    def hline(self, x0: float, x1: float, y: float) -> None:
        self.lines.append((x0, y, x1, y))

    def vline(self, x: float, y0: float, y1: float) -> None:
        self.lines.append((x, y0, x, y1))


def _render(pages: list[_Page], title: str) -> bytes:
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(612, 792))
    c.setTitle(f"SYNTHETIC FIXTURE {title}")
    for page in pages:
        for x, y, size, s in page.items:
            c.setFont(FONT, size)
            c.drawString(x, y, s)
        c.setLineWidth(0.5)
        for x0, y0, x1, y1 in page.lines:
            c.line(x0, y0, x1, y1)
        c.showPage()
    c.save()
    return out.getvalue()


def _grid(
    page: _Page,
    *,
    top: float,
    label_x: float,
    first_right: float,
    pitch: float,
    headers: list[str],
    labels: list[str],
    values: list[list[str]],
    hrules: bool,
    body_gap: float = LEAD,
) -> tuple[dict[tuple[int, int], str], BBox, float]:
    """A borderless (or horizontally ruled) table: header line at `top`, body rows below. Returns values, bbox, bottom y."""
    rights = [first_right + i * pitch for i in range(len(headers))]
    for x1, h in zip(rights, headers, strict=True):
        page.right(x1, top, h)
    cells: dict[tuple[int, int], str] = {}
    y = top
    for r, (label, row) in enumerate(zip(labels, values, strict=True)):
        y = top - body_gap - r * LEAD
        page.text(label_x, y, label)
        for c, (x1, v) in enumerate(zip(rights, row, strict=True)):
            page.right(x1, y, v)
            cells[(r, c)] = v
    right = rights[-1]
    if hrules:
        page.hline(label_x, right, top + SIZE + 2)
        page.hline(label_x, right, top - 4)
        page.hline(label_x, right, y - 4)
    return cells, (label_x, y - 4, right, top + SIZE + 2), y


_PROSE = [
    "SYNTHETIC FIXTURE prose line about upside risks to the central projection, first line of five.",
    "SYNTHETIC FIXTURE prose line continuing the discussion of the outlook without any figures in it.",
    "SYNTHETIC FIXTURE prose line that says the projection could be stronger if demand recovers.",
    "SYNTHETIC FIXTURE prose line that keeps the same column, leading and width as the others.",
    "SYNTHETIC FIXTURE prose line ending the paragraph above the table caption.",
]
_YEARS = ["2021", "2022", "2023", "2024", "2025", "2026f", "2027f", "2028f"]
_P5_LABELS = ["Output growth (annual avg %)", "Prices (annual %)", "Jobless rate", "Policy rate"]
_P5_VALUES = [
    ["5.6", "2.4", "0.7", "-0.5", "1.3", "2.2", "2.9", "2.6"],
    ["5.9", "7.2", "4.7", "2.2", "2.7", "2.4", "2.1", "2.0"],
    ["3.2", "3.4", "4.0", "5.1", "5.3", "4.9", "4.6", "4.4"],
    ["0.75", "4.25", "5.50", "4.25", "2.25", "2.25", "2.75", "3.25"],
]


def _p5(hrules: bool) -> tuple[list[_Page], list[TruthTable]]:
    page = _Page()
    for i, line in enumerate(_PROSE):
        page.text(60, 700 - i * 11, line, 9)
    page.text(60, 640, "Table 1: Synthetic central projections", 9)  # 4 em below the paragraph
    top = 620
    cells, bbox, bottom = _grid(
        page,
        top=top,
        label_x=60,
        first_right=250,
        pitch=42,
        headers=_YEARS,
        labels=_P5_LABELS,
        values=_P5_VALUES,
        hrules=hrules,
    )
    # Footnote marker on the first row label: a raised small digit right after the label.
    x_end = 60 + stringWidth(_P5_LABELS[0], FONT, SIZE)
    page.text(x_end + 0.5, top - LEAD + 3, "1", SMALL)
    # Notes: a small digit alone on its line at the row-label column, its definition right of it, then a source line.
    page.text(60, bottom - 14, "1", SMALL)
    page.text(66, bottom - 22, "Synthetic production basis")
    page.text(60, bottom - 34, "Source: Synthetic Statistics Office, Other Forecaster")
    truth = TruthTable(
        page=1,
        bbox=bbox,
        row_labels=_P5_LABELS,
        col_headers=[[y] for y in _YEARS],
        values=cells,
        markers=[(0, "1")],
        notes=["Synthetic production basis", "Source: Synthetic Statistics Office, Other Forecaster"],
    )
    return [page], [truth]


_QUARTERS = ["Dec-26", "Mar-27", "Jun-27", "Sep-27", "Dec-27", "Mar-28", "Jun-28", "Sep-28"]
_FX_LABELS = ["Pair A", "Pair B", "Pair C", "Pair D", "Pair E", "Index F"]
_RATE_LABELS = ["OCR", "Bill rate", "Swap rate", "Bond rate"]


def _values(rows: int, base: float, step: float) -> list[list[str]]:
    return [[f"{base + r * 0.111 + c * step:.3f}" for c in range(9)] for r in range(rows)]


def _stacked_table(
    page: _Page, *, top: float, caption: str, labels: list[str], values: list[list[str]], hrules: bool
) -> tuple[TruthTable, float]:
    page.text(60, top + 22, caption, 9)
    headers = ["", *_QUARTERS]  # the stacked column has no fragment on the period line
    cells, bbox, bottom = _grid(
        page,
        top=top,
        label_x=60,
        first_right=200,
        pitch=44,
        headers=headers,
        labels=labels,
        values=values,
        hrules=hrules,
        body_gap=LEAD + 0.61 * SIZE,  # the stacked date line sits between the period line and the body
    )
    page.items[:] = [it for it in page.items if it[3] != ""]
    # "Current" 0.59 em above the period line and a bracketed date 0.61 em below it, both over column 0.
    page.right(200, top + 0.59 * SIZE, "Current")
    page.right(200, top - 0.61 * SIZE, "(11 Nov)")
    col_headers = [["Current", "(11 Nov)"], *[[q] for q in _QUARTERS]]
    return (
        TruthTable(page=1, bbox=bbox, row_labels=labels, col_headers=col_headers, values=cells, stacked=[0]),
        bottom,
    )


def _p8(hrules: bool) -> tuple[list[_Page], list[TruthTable]]:
    page = _Page()
    fx, bottom = _stacked_table(
        page,
        top=690,
        caption="Synthetic exchange rates (end of period) Forecasts",
        labels=_FX_LABELS,
        values=_values(6, 0.5, 0.004),
        hrules=hrules,
    )
    rates, _ = _stacked_table(
        page,
        top=bottom - 60,
        caption="Synthetic interest rates (end of period)",
        labels=_RATE_LABELS,
        values=_values(4, 2.25, 0.05),
        hrules=hrules,
    )
    return [page], [fx, rates]


def _ruled() -> tuple[list[_Page], list[TruthTable]]:
    page = _Page()
    xs = [60, 200, 260, 320]
    top = 700
    rows = [["Indicator", "2026", "2027"], ["Measure A", "1.5", "1.8"], ["Measure B", "3.25", "3.50"]]
    for r, row in enumerate(rows):
        y = top - r * 18
        page.text(xs[0] + 3, y, row[0])
        for c in (1, 2):
            page.right(xs[c + 1] - 3, y, row[c])
    y_lines = [top + 12 - r * 18 for r in range(4)]
    for y in y_lines:
        page.hline(xs[0], xs[-1], y)
    for x in xs:
        page.vline(x, y_lines[-1], y_lines[0])
    truth = TruthTable(
        page=1,
        bbox=(xs[0], y_lines[-1], xs[-1], y_lines[0]),
        row_labels=["Measure A", "Measure B"],
        col_headers=[["2026"], ["2027"]],
        values={(0, 0): "1.5", (0, 1): "1.8", (1, 0): "3.25", (1, 1): "3.50"},
    )
    return [page], [truth]


def _small_table(page: _Page, top: float, values: list[list[str]], first_right: float, pitch: float):
    labels = ["Measure A", "Measure B", "Measure C"]
    return _grid(
        page,
        top=top,
        label_x=60,
        first_right=first_right,
        pitch=pitch,
        headers=["2026f", "2027f", "2028f"],
        labels=labels,
        values=values,
        hrules=False,
    ), labels


_SMALL_VALUES = [["1.2", "1.4", "1.6"], ["2.5", "2.7", "2.9"], ["4.0", "4.1", "4.2"]]


def _fused() -> tuple[list[_Page], list[TruthTable]]:
    page = _Page()
    page.text(60, 720, "Table 2: Synthetic projections", 9)
    (cells, bbox, bottom), labels = _small_table(page, 700, _SMALL_VALUES, 220, 50)
    # A raised small marker directly after the value at row 1, column 0 ("2.5" then "1").
    x1 = 220
    page.text(x1 + 0.3, 700 - 2 * LEAD + 3, "1", SMALL)
    page.text(60, bottom - 14, "1", SMALL)
    page.text(66, bottom - 22, "Synthetic definition")
    truth = TruthTable(
        page=1,
        bbox=bbox,
        row_labels=labels,
        col_headers=[["2026f"], ["2027f"], ["2028f"]],
        values=cells,
        value_markers={(1, 0): "1"},
        notes=["Synthetic definition"],
    )
    return [page], [truth]


def _axis_noise() -> tuple[list[_Page], list[TruthTable]]:
    page = _Page()
    # A chart above the table: y-axis ticks in a column and x-axis years in a row, no table.
    for i, tick in enumerate(["0", "1", "2", "3", "4", "5"]):
        page.right(70, 600 + i * 25, tick)
    for i, year in enumerate(["2019", "2020", "2021", "2022", "2023"]):
        page.text(90 + i * 60, 585, year)
    page.text(60, 540, "Table 3: Synthetic projections", 9)
    (cells, bbox, _), labels = _small_table(page, 520, _SMALL_VALUES, 220, 50)
    truth = TruthTable(
        page=1, bbox=bbox, row_labels=labels, col_headers=[["2026f"], ["2027f"], ["2028f"]], values=cells
    )
    return [page], [truth]


_TIGHT_VALUES = [["12.35", "13.40", "14.65"], ["22.50", "24.75", "26.00"], ["31.25", "32.50", "33.75"]]


def _tight() -> tuple[list[_Page], list[TruthTable]]:
    page = _Page()
    page.text(60, 720, "Table 4: Synthetic projections", 9)
    # Pitch = widest value + 0.5 em: two value columns nearly touch.
    # Pitch = widest header + 0.5 em, values as wide as the headers: two value columns nearly touch.
    pitch = stringWidth("2028f", FONT, SIZE) + 0.5 * SIZE
    (cells, bbox, _), labels = _small_table(page, 700, _TIGHT_VALUES, 220, pitch)
    truth = TruthTable(
        page=1, bbox=bbox, row_labels=labels, col_headers=[["2026f"], ["2027f"], ["2028f"]], values=cells
    )
    return [page], [truth]


def _case(name: str, built: tuple[list[_Page], list[TruthTable]]) -> Case:
    pages, truth = built
    items = [it for p in pages for it in p.items]
    lines = [ln for p in pages for ln in p.lines]
    return Case(name=name, pdf=_render(pages, name), truth=truth, items=items, lines=lines)


def cases() -> list[Case]:
    return [
        _case("p5_annual", _p5(hrules=False)),
        _case("p5_annual_hrules", _p5(hrules=True)),
        _case("p8_stacked", _p8(hrules=False)),
        _case("p8_stacked_hrules", _p8(hrules=True)),
        _case("ruled_control", _ruled()),
        _case("fused_superscript", _fused()),
        _case("axis_noise", _axis_noise()),
        _case("tight_columns", _tight()),
    ]

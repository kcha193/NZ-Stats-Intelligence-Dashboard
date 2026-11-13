"""Forecast freshness (Phase 4AH): a bank's older figure is not shown as current beside a newer report not fully read.

A refused table cell has no identity (only a code and a position), so freshness is judged per document: a newer
quarterly outlook report that was not fully read hides the bank's older figures for every measure that report, or a
later one, does not restate. Nothing is inferred about what a refused cell was. Synthetic PDFs only; no network.
"""

from datetime import date

import pytest

from nzstats.research.bank_view import bank_view
from nzstats.research.banks import BankAdapter, Series
from nzstats.research.drafts import DraftAllowlist
from nzstats.research.manual_import import import_document
from nzstats.research.table_ingest import extract_version_tables
from nzstats.sources.artifacts import ArtifactStore

from .conftest import NOW
from .pdf_table_support import table_pdf
from .support import BASE, institution
from .test_drafts_auto import auto
from .test_table_forecast import line, page
from .test_table_grid import COLS
from .test_table_ingest import APPROVED, no_network  # noqa: F401 (autouse guard)

ADAPTERS = {
    "example": BankAdapter(
        "example", (Series("outlook", "Outlook", "outlook", 100, url_pattern=r"outlook-2026"),)
    )
}
INST = institution(**APPROVED)
REGISTRY = {INST.key: INST}
AUG, NOV = date(2026, 8, 1), date(2026, 11, 1)
URL_AUG = f"{BASE}/research/outlook-2026-08.pdf"
URL_NOV = f"{BASE}/research/outlook-2026-11.pdf"
SOURCE = (72, 650, "Source: Example Research")


@pytest.fixture()
def artifacts(tmp_path):
    return ArtifactStore(tmp_path / "raw")


def report(cpi=("4", "3", "2.6", "2.2"), ocr=("4.25", "3.75", "3.25", "3.00"), extra=()):
    rows = [*line(686, "OCR (%)", list(ocr)), *line(672, "Annual CPI inflation (%)", list(cpi))]
    return table_pdf([page(rows, extra=[SOURCE, *extra])])


def footnoted():
    """The newer report's June CPI figure carries a footnote marker: refused, identity not recorded."""
    return report(cpi=("4", "3", "2.4*", "2.1"), extra=[(72, 636, "* Excludes petrol")])


def ambiguous():
    """OCR in a clean table; CPI in a second table whose row is shifted between columns: that table is refused whole."""
    shifted = [x + 30 for x in COLS]
    clean = page(line(686, "OCR (%)", ["4.25", "3.50", "3.00", "2.75"]), extra=[SOURCE])
    bad = page(line(686, "Annual CPI inflation (%)", ["4", "3", "2.4", "2.1"], shifted), extra=[SOURCE])
    return table_pdf([clean, bad])


def held(conn, artifacts, body, *, published=NOV, url=URL_NOV, extract=True):
    result = import_document(conn, INST, body=body, file_format="pdf", url=url, importer="Test Owner",
                             note="saved from a browser", now=NOW, artifacts=artifacts, published_on=published)  # fmt: skip
    if extract:
        extract_version_tables(conn, result.version_id, artifacts, REGISTRY, NOW, isolate=False)
    return result.version_id


def view(conn, allowlist=None, registry=REGISTRY):
    return bank_view(conn, registry, allowlist or auto(), ADAPTERS)


def states(conn, **kw):
    return {(s.published_on, s.state) for s in view(conn, **kw).documents}


# --- document states -------------------------------------------------------------------------------------------------


def test_a_clean_extraction_is_read(conn, artifacts):
    held(conn, artifacts, report())
    assert states(conn) == {("2026-11-01", "read")}


@pytest.mark.parametrize("body", [footnoted, ambiguous], ids=["footnote", "ambiguous_columns"])
def test_a_refused_cell_makes_the_report_incomplete(conn, artifacts, body):
    held(conn, artifacts, body())
    assert states(conn) == {("2026-11-01", "incomplete")}


def test_a_dash_in_an_own_forecast_cell_makes_the_report_incomplete(conn, artifacts):
    held(conn, artifacts, report(cpi=("4", "3", "-", "2.1")))
    assert states(conn) == {("2026-11-01", "incomplete")}


def test_a_refused_scenario_table_affects_scenario_groups_only(conn, artifacts):
    central = page(line(686, "OCR (%)", ["4.25", "3.50", "3.00", "2.75"]), extra=[SOURCE])
    scenario = page(line(686, "OCR (%)", ["4.25", "3.00", "2.50", "2.00"]),
                    extra=[SOURCE, (72, 730, "Downside scenario")])  # fmt: skip
    vid = held(conn, artifacts, table_pdf([central, scenario]))
    codes = [r["code"] for r in conn.execute(
        "SELECT r.code FROM research_table_rejection r JOIN research_table_extraction e ON e.id = r.extraction_id"
        " WHERE e.version_id = ?", (vid,))]  # fmt: skip
    assert codes and set(codes) <= {"scenario_table", "scenario_row", "scenario_column"}
    assert states(conn) == {("2026-11-01", "incomplete_scenario")}


def test_a_held_report_never_extracted_is_not_read(conn, artifacts):
    held(conn, artifacts, report(), extract=False)
    assert states(conn) == {("2026-11-01", "not_read")}


def test_a_report_read_only_by_an_older_interpreter_is_not_read(conn, artifacts):
    vid = held(conn, artifacts, report(), extract=False)
    from nzstats.research.table_store import store_extraction

    from .test_table_store import SHA, tf

    store_extraction(conn, vid, NOW, [tf()], [], words_sha256=SHA, interpreter_version="tables-12")
    assert states(conn) == {("2026-11-01", "not_read")}


def test_without_the_automatic_view_table_figures_do_not_count_as_read(conn, artifacts):
    held(conn, artifacts, report())
    assert states(conn, allowlist=DraftAllowlist()) == {("2026-11-01", "not_read")}


def test_a_report_with_no_table_figure_at_all_is_not_read(conn, artifacts):
    prose = table_pdf([[(72, 700, "The economy is slowing and inflation is easing over the year ahead.")]])
    held(conn, artifacts, prose)
    assert states(conn) == {("2026-11-01", "not_read")}


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE research_document_version SET superseded_at = '2026-11-02T00:00:00Z' WHERE id = ?",
        "UPDATE research_publication SET duplicate_of_id = id WHERE current_version_id = ?",
        "UPDATE research_publication SET published_on = NULL WHERE current_version_id = ?",
    ],
    ids=["superseded", "duplicate", "undated"],
)
def test_a_report_that_cannot_be_placed_or_shown_has_no_state(conn, artifacts, change):
    vid = held(conn, artifacts, footnoted())
    conn.execute(change, (vid,))
    assert states(conn) == set()


def withdraw(conn, artifacts, vid):
    from nzstats.research import purge

    plan = purge.plan_purge(conn, INST.key, version_ids=[vid])
    purge.apply_purge(conn, plan, artifacts, reason="permission_withdrawn", purged_by="Test Owner",
                      note="synthetic withdrawal", now=NOW)  # fmt: skip


def test_a_withdrawn_purged_report_has_no_state(conn, artifacts):
    withdraw(conn, artifacts, held(conn, artifacts, footnoted()))
    assert states(conn) == set()


def test_a_newer_weekly_note_has_no_state(conn, artifacts):
    held(conn, artifacts, footnoted(), url=f"{BASE}/research/weekly-2026-11.pdf")
    assert states(conn) == set()


def test_a_revoked_route_has_no_state(conn, artifacts):
    held(conn, artifacts, footnoted())
    revoked = institution(**{**APPROVED, "manual_import": "denied", "manual_import_approved_by": None,
                             "manual_import_approved_on": None, "manual_import_note": None})  # fmt: skip
    assert states(conn, registry={revoked.key: revoked}) == set()

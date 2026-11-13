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
    key: BankAdapter(
        key, (Series("outlook", "Outlook", "outlook", 100, url_pattern=r"outlook-2026"),)
    )
    for key in ("example", "other")
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
    bad = [
        (72, 745, "Table 2: Inflation (SYNTHETIC FIXTURE)"),
        *line(700, "", ["Dec-25", "Mar-26", "Jun-26", "Sep-26"]),
        *line(686, "OCR (%)", ["4.25", "3.50", "3.00", "2.75"]),
        *line(672, "Annual CPI inflation (%)", ["4", "3", "2.4", "2.1"], shifted),
    ]
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
    prose = table_pdf(
        [[(72, 700, "The economy is slowing and inflation is easing over the year ahead.")]]
    )
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


@pytest.mark.parametrize(
    "overrides",
    [
        {"manual_import": "denied", "manual_import_approved_by": None,
         "manual_import_approved_on": None, "manual_import_note": None},
    ],
    ids=["route_revoked"],
)  # fmt: skip
def test_a_held_report_that_may_not_be_shown_is_not_read(conn, artifacts, overrides):
    held(conn, artifacts, report())
    narrowed = institution(**{**APPROVED, **overrides})
    assert states(conn, registry={narrowed.key: narrowed}) == {("2026-11-01", "not_read")}


def direct(conn, allowlist, read):
    from nzstats.research.table_view import document_states

    return {
        (s.published_on, s.state)
        for s in document_states(conn, REGISTRY, allowlist, read, ADAPTERS)
    }


def test_an_admitted_summary_does_not_make_a_stale_table_reading_read(conn, artifacts):
    vid = held(conn, artifacts, report(), extract=False)
    from nzstats.research.table_store import store_extraction

    from .test_table_store import SHA, tf

    store_extraction(conn, vid, NOW, [tf()], [], words_sha256=SHA, interpreter_version="tables-12")
    assert direct(conn, auto(), {vid}) == {("2026-11-01", "not_read")}
    assert direct(conn, DraftAllowlist(), {vid}) == {("2026-11-01", "not_read")}


def test_an_admitted_summary_with_no_table_reading_is_read(conn, artifacts):
    vid = held(
        conn, artifacts, report(), extract=False
    )  # Phase 4AE: the checked model reading is the reading
    assert direct(conn, auto(), {vid}) == {("2026-11-01", "read")}


def test_a_refused_cell_counts_in_the_named_mode_too(conn, artifacts):
    vid = held(conn, artifacts, footnoted())
    assert direct(conn, DraftAllowlist(), {vid}) == {("2026-11-01", "incomplete")}
    clean = held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    assert ("2026-08-01", "not_read") in direct(
        conn, DraftAllowlist(), {vid}
    )  # tables alone do not show there
    assert ("2026-08-01", "read") in direct(conn, DraftAllowlist(), {vid, clean})


# --- the rule in the analytics ---------------------------------------------------------------------------------------

JUNE, SEPT = "Year to June 2026", "Year to September 2026"
NEWER = {"newer_report_incomplete", "newer_report_not_read"}


def current(v, indicator="cpi_inflation", horizon=JUNE):
    """(published_on, value, earlier values) of the bank's current figure in the comparison, or None."""
    from nzstats.research.bank_analytics import bank_comparison

    for _, comparison in bank_comparison(v):
        for g in comparison.groups:
            if g.indicator == indicator and g.horizon_label == horizon and g.kind == "central":
                (row,) = g.rows
                return (
                    row.forecast.published_on,
                    row.forecast.value,
                    [e.value for e in row.earlier_vintages],
                )
    return None


def codes(v, **kw):
    from nzstats.research.bank_analytics import bank_exclusions

    kw = {"outlook_only": False, "dated_only": False, **kw}
    return sorted({e.code for e in bank_exclusions(v, **kw)} & NEWER)


def consensus_values(v, horizon=JUNE):
    from nzstats.research.bank_analytics import bank_consensus

    c = bank_consensus(v)
    found = [g for g in c.groups if g.indicator == "cpi_inflation" and g.horizon_label == horizon]
    return [x.value for g in found for x in g.contributors], sorted(
        {e.code for e in c.excluded} & NEWER
    )


def history(v, horizon=JUNE):
    from nzstats.research.bank_analytics import bank_revisions

    return [
        [x.value for x in s.vintages]
        for _, h in bank_revisions(v)
        for s in h.series
        if s.indicator == "cpi_inflation" and s.horizon_label == horizon
    ]


def test_a_newer_valid_report_is_current_and_the_older_figure_is_an_earlier_vintage(
    conn, artifacts
):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    held(conn, artifacts, report(cpi=("4", "3", "2.4", "2.1")))
    v = view(conn)
    assert current(v) == ("2026-11-01", 2.4, [2.6])
    assert codes(v) == [] and consensus_values(v) == ([2.4], [])
    assert history(v) == [[2.6, 2.4]]


def test_a_refused_cell_in_the_newer_report_stops_the_older_figure_appearing_current(
    conn, artifacts
):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    held(conn, artifacts, footnoted())
    v = view(conn)
    assert (
        current(v) is None
    )  # June: the newer report's cell was refused, so there is no current June figure
    assert current(v, horizon=SEPT) == ("2026-11-01", 2.1, [2.2])  # restated: an ordinary revision
    assert codes(v) == ["newer_report_incomplete"]
    assert consensus_values(v) == ([], ["newer_report_incomplete"])  # never used in the consensus
    assert history(v) == [[2.6]]  # what the bank said in August stays in the history


def test_an_ambiguous_refused_table_hides_only_what_the_newer_report_does_not_restate(
    conn, artifacts
):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    held(conn, artifacts, ambiguous())
    v = view(conn)
    assert current(v) is None and current(v, horizon=SEPT) is None
    assert current(v, "ocr", "June 2026 quarter") == ("2026-11-01", 3.0, [3.25])
    assert codes(v) == ["newer_report_incomplete"]


def test_a_dash_in_the_newer_report_stops_the_older_figure_appearing_current(conn, artifacts):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    held(conn, artifacts, report(cpi=("4", "3", "-", "2.1")))
    v = view(conn)
    assert current(v) is None and current(v, horizon=SEPT) == ("2026-11-01", 2.1, [2.2])
    assert codes(v) == ["newer_report_incomplete"]


def test_a_newer_report_not_yet_read_stops_older_figures_appearing_current(conn, artifacts):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    held(conn, artifacts, report(cpi=("4", "3", "2.4", "2.1")), extract=False)
    v = view(conn)
    assert current(v) is None and current(v, "ocr", "June 2026 quarter") is None
    assert codes(v) == ["newer_report_not_read"]
    assert consensus_values(v) == ([], ["newer_report_not_read"])
    assert history(v) == [[2.6]]


def test_the_history_views_keep_every_accepted_vintage(conn, artifacts):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    held(conn, artifacts, footnoted())
    v = view(conn)
    assert codes(v, outlook_only=True, dated_only=True, current=False) == []


def test_a_duplicate_newer_report_changes_nothing(conn, artifacts):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    vid = held(conn, artifacts, footnoted())
    conn.execute(
        "UPDATE research_publication SET duplicate_of_id ="
        " (SELECT id FROM research_publication WHERE canonical_url = ?) WHERE current_version_id = ?",
        (URL_AUG, vid),
    )
    v = view(conn)
    assert current(v) == ("2026-08-01", 2.6, []) and codes(v) == []


def test_a_corrected_newer_report_is_judged_on_its_corrected_version(conn, artifacts):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    held(conn, artifacts, footnoted())
    corrected = held(conn, artifacts, report(cpi=("4", "3", "2.5", "2.1")), extract=False)
    v = view(conn)  # the refused original is superseded; the correction is held but not yet read
    assert current(v) is None and codes(v) == ["newer_report_not_read"]
    extract_version_tables(conn, corrected, artifacts, REGISTRY, NOW, isolate=False)
    v = view(conn)
    assert current(v) == ("2026-11-01", 2.5, [2.6]) and codes(v) == []


def test_a_withdrawn_newer_report_leaves_the_older_figure_as_the_latest(conn, artifacts):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    withdraw(conn, artifacts, held(conn, artifacts, footnoted()))
    v = view(conn)
    assert current(v) == ("2026-08-01", 2.6, []) and codes(v) == []


def test_a_still_newer_report_that_restates_the_measure_makes_the_older_figure_an_earlier_vintage(
    conn, artifacts
):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    held(conn, artifacts, footnoted())
    held(conn, artifacts, report(cpi=("4", "3", "2.3", "2.0")), published=date(2026, 12, 1),
         url=f"{BASE}/research/outlook-2026-12.pdf")  # fmt: skip
    v = view(conn)
    assert current(v) == ("2026-12-01", 2.3, [2.6]) and codes(v) == []


def test_a_refused_scenario_table_leaves_central_figures_current(conn, artifacts):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    central = page(line(686, "OCR (%)", ["4.25", "3.50", "3.00", "2.75"]), extra=[SOURCE])
    scenario = page(line(686, "OCR (%)", ["4.25", "3.00", "2.50", "2.00"]),
                    extra=[SOURCE, (72, 730, "Downside scenario")])  # fmt: skip
    held(conn, artifacts, table_pdf([central, scenario]))
    assert ("2026-11-01", "incomplete_scenario") in states(conn)
    v = view(conn)
    assert current(v) == ("2026-08-01", 2.6, []) and codes(v) == []


@pytest.mark.parametrize("where", ["weekly", "undated"])
def test_a_newer_weekly_or_undated_report_changes_nothing(conn, artifacts, where):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    url = f"{BASE}/research/weekly-2026-11.pdf" if where == "weekly" else URL_NOV
    vid = held(conn, artifacts, footnoted(), url=url)
    if where == "undated":
        conn.execute(
            "UPDATE research_publication SET published_on = NULL WHERE current_version_id = ?",
            (vid,),
        )
    v = view(conn)
    assert current(v) == ("2026-08-01", 2.6, []) and codes(v) == []


# --- latest published versus latest accepted -------------------------------------------------------------------------


def vintages(v):
    from nzstats.research.bank_analytics import bank_vintages

    return [(x.institution_key, x.latest_published_on, x.latest_accepted_on, x.state, x.current)
            for x in bank_vintages(v)]  # fmt: skip


def test_a_clean_newest_report_is_current(conn, artifacts):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    held(conn, artifacts, report(cpi=("4", "3", "2.4", "2.1")))
    assert vintages(view(conn)) == [("example", "2026-11-01", "2026-11-01", "read", True)]


def test_a_partly_refused_newest_report_is_published_but_not_current(conn, artifacts):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    held(conn, artifacts, footnoted())
    assert vintages(view(conn)) == [("example", "2026-11-01", "2026-11-01", "incomplete", False)]


def test_an_unread_newest_report_leaves_the_latest_accepted_older(conn, artifacts):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    held(conn, artifacts, report(cpi=("4", "3", "2.4", "2.1")), extract=False)
    assert vintages(view(conn)) == [("example", "2026-11-01", "2026-08-01", "not_read", False)]


def test_a_bank_with_no_dated_outlook_report_has_no_vintage_row(conn, artifacts):
    held(conn, artifacts, report(), url=f"{BASE}/research/weekly-2026-11.pdf")
    assert vintages(view(conn)) == []


def test_one_banks_unread_report_does_not_hide_another_banks_figures(conn, artifacts):
    other = institution("other", **APPROVED)
    registry = {**REGISTRY, other.key: other}
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    import_document(conn, other, body=report(cpi=("4", "3", "2.5", "2.0")), file_format="pdf",
                    url=f"{BASE}/research/other-outlook-2026-11.pdf", importer="Test Owner",
                    note="saved from a browser", now=NOW, artifacts=artifacts, published_on=NOV)  # fmt: skip
    v = view(conn, registry=registry)
    assert ("other", "not_read") in {(s.institution_key, s.state) for s in v.documents}
    assert current(v) == ("2026-08-01", 2.6, []) and codes(v) == []


def test_an_undated_figure_is_not_current_beside_a_newer_unread_report(conn, artifacts):
    old = held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    conn.execute(
        "UPDATE research_publication SET published_on = NULL WHERE current_version_id = ?", (old,)
    )
    held(conn, artifacts, report(cpi=("4", "3", "2.4", "2.1")), extract=False)
    v = view(conn)  # an undated figure cannot be shown to be newer than the unread report
    assert current(v) is None and codes(v) == ["newer_report_not_read"]


def test_latest_accepted_ignores_figures_the_analysis_refuses(conn, artifacts):
    held(conn, artifacts, report(), published=AUG, url=URL_AUG)
    first = page(line(686, "Annual CPI inflation (%)", ["4", "3", "2.4", "2.1"]), extra=[SOURCE])
    second = [(72, 745, "Table 2: Inflation (SYNTHETIC FIXTURE)"),
              *page(line(686, "Annual CPI inflation (%)", ["4", "3", "2.9", "2.7"]), extra=[SOURCE])]  # fmt: skip
    held(
        conn, artifacts, table_pdf([first, second])
    )  # the newest report contradicts itself on every figure
    assert ("2026-11-01", "read") in states(conn)
    assert vintages(view(conn)) == [("example", "2026-11-01", "2026-08-01", "read", False)]

"""Table figures reaching the bank analytics (Phase 4AF): gated like the drafts, reconciled, and never guessed."""

from datetime import date

import pytest

from nzstats.research.bank_analytics import bank_comparison, bank_exclusions
from nzstats.research.bank_view import bank_view
from nzstats.research.banks import BankAdapter, Series
from nzstats.research.manual_import import import_document
from nzstats.research.table_ingest import extract_version_tables
from nzstats.research.table_reconcile import summary_counts
from nzstats.research.table_view import table_forecasts
from nzstats.sources.artifacts import ArtifactStore

from .bank_support import nf
from .conftest import NOW
from .pdf_table_support import table_pdf
from .support import institution
from .test_drafts_auto import auto
from .test_table_forecast import line, page
from .test_table_ingest import APPROVED, URL, no_network  # noqa: F401 (autouse guard)

ADAPTERS = {
    "example": BankAdapter(
        "example", (Series("outlook", "Outlook", "outlook", 100, url_pattern=r"outlook-2026"),)
    )
}


@pytest.fixture()
def artifacts(tmp_path):
    return ArtifactStore(tmp_path / "raw")


def pdf(
    cpi=("4", "3", "2.6", "2.2"),
    source="Source: Example Research",
    ocr=("4.25", "3.75", "3.25", "3.00"),
):
    rows = [*line(686, "OCR (%)", list(ocr)), *line(672, "Annual CPI inflation (%)", list(cpi))]
    return table_pdf([page(rows, extra=[(72, 650, source)] if source else [])])


def stored(conn, artifacts, body=None, *, published=date(2026, 10, 1), **overrides):
    inst = institution(**{**APPROVED, **overrides})
    result = import_document(conn, inst, body=body or pdf(), file_format="pdf", url=URL, importer="Test Owner",
                             note="saved from a browser", now=NOW, artifacts=artifacts, published_on=published)  # fmt: skip
    registry = {inst.key: inst}
    extract_version_tables(conn, result.version_id, artifacts, registry, NOW, isolate=False)
    return registry, result.version_id


def claim(v, value=2.6, **kw):
    kw.setdefault("published_on", "2026-10-01")
    return nf(
        "example",
        summary_id=v,
        value=value,
        horizon="year to June 2026",
        indicator_label="Annual CPI inflation",
        **kw,
    )


def run(conn, registry, claims=(), allowlist=None):
    return table_forecasts(conn, registry, list(claims), allowlist or auto(), ADAPTERS)


def cpi_june(forecasts):
    return [
        f
        for f in forecasts
        if f.forecast.indicator == "cpi_inflation" and f.forecast.horizon == "year to June 2026"
    ]


def test_forecast_rows_become_normalized_forecasts_with_their_cell_as_evidence(conn, artifacts):
    registry, v = stored(conn, artifacts)
    forecasts, excluded, _ = run(conn, registry)
    assert len(forecasts) == 4 and excluded == []
    n = cpi_june(forecasts)[0]
    assert (n.extraction_method, n.institution_key, n.report_kind, n.adjustment, n.geography) == (
        "table", "example", "outlook", "not_stated", "New Zealand")  # fmt: skip
    assert (
        n.forecast.summary_id < 0
        and n.claim_path.startswith("tables[")
        and n.document_version_id == v
    )
    assert (n.forecast.value, n.raw_value, n.forecast.unit, n.forecast.direction) == (
        2.6,
        2.6,
        "percent",
        "unclear",
    )
    assert n.forecast.published_on == "2026-10-01" and n.verifier_version == "tables-2"
    (e,) = n.forecast.evidence
    assert (
        e.page == 1
        and "2.6" in e.quote
        and "Annual CPI inflation" in e.quote
        and "Jun-26" in e.quote
    )


def test_actuals_and_missing_figures_are_not_forecasts(conn, artifacts):
    body = pdf(cpi=("4.00", "-", "2.0", "-"), ocr=("4", "3", "-", "-"))
    registry, _ = stored(conn, artifacts, body)
    forecasts, excluded, _ = run(conn, registry)
    assert [(f.forecast.indicator, f.forecast.value) for f in forecasts] == [("cpi_inflation", 2.0)]
    assert excluded == []


def test_only_the_auto_gate_shows_table_figures(conn, artifacts):
    from nzstats.research.drafts import DraftAllowlist

    registry, _ = stored(conn, artifacts)
    assert run(conn, registry, allowlist=DraftAllowlist())[0] == []


def test_legacy_extractions_do_not_reach_analytics(conn):
    from nzstats.research.table_store import store_extraction

    from .llm_support import seed_version
    from .test_table_store import SHA, tf

    v = seed_version(conn)
    store_extraction(conn, v, NOW, [tf()], [], words_sha256=SHA, interpreter_version="tables-1")
    inst = institution(min_text_chars=20)
    assert run(conn, {inst.key: inst}) == ([], [], [])


@pytest.mark.parametrize(
    "change",
    [
        lambda c, v: c.execute(
            "UPDATE research_document_version SET superseded_at = '2026-10-02T00:00:00Z' WHERE id = ?",
            (v,),
        ),
        lambda c, v: c.execute("UPDATE research_publication SET duplicate_of_id = id"),
    ],
    ids=["superseded", "duplicate"],
)
def test_a_document_that_is_not_the_current_one_shows_nothing(conn, artifacts, change):
    registry, v = stored(conn, artifacts)
    change(conn, v)
    assert run(conn, registry)[0] == []


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "manual_import": "denied",
            "manual_import_approved_by": None,
            "manual_import_approved_on": None,
            "manual_import_note": None,
        },
        {"kind": "government"},
    ],
    ids=["route_revoked", "not_a_bank"],
)
def test_a_source_that_is_no_longer_permitted_or_not_a_bank_shows_nothing(
    conn, artifacts, overrides
):
    registry, _ = stored(conn, artifacts)
    changed = institution(**{**APPROVED, **overrides})
    assert run(conn, {changed.key: changed})[0] == []


def test_content_policy_is_rechecked_on_every_read(conn):
    from nzstats.research.table_store import store_extraction

    from .llm_support import seed_version
    from .test_table_store import SHA, tf

    v = seed_version(conn)  # held through the (approved) crawler route
    store_extraction(conn, v, NOW, [tf()], [], words_sha256=SHA)
    full = institution(min_text_chars=20)
    assert len(run(conn, {full.key: full})[0]) == 1
    narrowed = institution(content_policy="metadata_only", min_text_chars=20)
    assert run(conn, {narrowed.key: narrowed})[0] == []


def test_an_agreeing_claim_is_the_one_statement_so_the_table_duplicate_is_not_added(
    conn, artifacts
):
    registry, v = stored(conn, artifacts)
    forecasts, excluded, recs = run(conn, registry, [claim(v, 2.6)])
    assert (
        cpi_june(forecasts) == [] and excluded == []
    )  # the checked claim already states it; nothing is counted twice
    assert len(forecasts) == 3  # the other three table figures have no counterpart and stand
    assert summary_counts(recs) == {"exact_match": 1, "no_counterpart": 3}


def test_a_contradicting_claim_leaves_both_in_so_the_analytics_can_refuse_both(conn, artifacts):
    registry, v = stored(conn, artifacts)
    forecasts, _, recs = run(conn, registry, [claim(v, 3.1)])
    assert len(cpi_june(forecasts)) == 1 and "contradictory_value" in {r.cls for r in recs}


def test_a_rounding_difference_keeps_the_claim_and_drops_the_table_figure(conn, artifacts):
    registry, v = stored(conn, artifacts, pdf(cpi=("4", "3", "2.65", "2.2")))
    forecasts, excluded, _ = run(conn, registry, [claim(v, 2.7)])
    assert cpi_june(forecasts) == []
    assert [e.code for e in excluded] == ["reconciliation_rounding"]
    assert (
        excluded[0].normalized is None
    )  # the bank's figure is the claim; nothing is hidden by this exclusion


@pytest.mark.parametrize(
    ("cpi", "extra"),
    [
        (("4", "3", "2.6", "2.2"), {"unit": "percentage_points"}),
        (("4", "3", "2.6", "-"), {"horizon": "year to September 2026"}),
    ],
    ids=["unit", "horizon"],
)
def test_a_mismatch_of_unit_or_horizon_is_left_unresolved_not_guessed(conn, artifacts, cpi, extra):
    registry, v = stored(conn, artifacts, pdf(cpi=cpi))
    c = nf("example", summary_id=v, value=2.6, published_on="2026-10-01", indicator_label="Annual CPI inflation",
           **{"horizon": "year to June 2026", **extra})  # fmt: skip
    forecasts, excluded, _ = run(conn, registry, [c])
    assert [e.code for e in excluded] == ["table_unresolved_reconciliation"]
    assert excluded[0].normalized is None and cpi_june(forecasts) == []


def test_a_table_attributed_to_someone_else_is_excluded(conn, artifacts):
    registry, _ = stored(conn, artifacts, pdf(source="Source: RBNZ"))
    forecasts, excluded, _ = run(conn, registry)
    assert (
        forecasts == []
        and {e.code for e in excluded} == {"table_third_party"}
        and len(excluded) == 4
    )


def test_through_bank_view_a_table_figure_joins_the_comparison(conn, artifacts):
    registry, v = stored(conn, artifacts)
    view = bank_view(conn, registry, auto(), ADAPTERS, drafts=[])
    ((_, comparison),) = [x for x in bank_comparison(view) if x[1].groups][:1]
    values = {r.forecast.value for g in comparison.groups for r in g.rows}
    assert 2.6 in values and {f.extraction_method for f in view.forecasts} == {"table"}


def test_a_table_figure_that_contradicts_a_claim_in_the_same_document_is_a_conflict_even_when_undated(
    conn, artifacts
):
    registry, v = stored(conn, artifacts, published=None)
    forecasts, _, _ = run(conn, registry, [claim(v, 3.1, published_on=None)])
    from .bank_support import view_of

    view = view_of(claim(v, 3.1, published_on=None), *forecasts)
    codes = [e.code for e in bank_exclusions(view, outlook_only=False, dated_only=False)]
    assert codes.count("conflicting_forecasts") == 2


def test_an_agreeing_claim_leaves_one_vintage_one_row_and_no_exclusion(conn, artifacts):
    from nzstats.research.bank_analytics import bank_revisions

    from .bank_support import view_of

    registry, v = stored(conn, artifacts)
    forecasts, _, _ = run(conn, registry, [claim(v, 2.6)])
    view = view_of(claim(v, 2.6), *forecasts)
    assert bank_exclusions(view, outlook_only=False, dated_only=False) == []
    ((_, comparison),) = [x for x in bank_comparison(view) if x[1].groups][:1]
    row = next(
        r for g in comparison.groups for r in g.rows if r.forecast.indicator == "cpi_inflation"
    )
    assert row.earlier_vintages == []
    series = next(
        s for _, h in bank_revisions(view) for s in h.series if s.indicator == "cpi_inflation"
    )
    assert len(series.vintages) == 1

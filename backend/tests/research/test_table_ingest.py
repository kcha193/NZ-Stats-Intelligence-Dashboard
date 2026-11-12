"""Extracting table figures from a stored PDF version (Phase 4AF): permitted, local, idempotent, content-free output."""

import json
import socket
import textwrap
from datetime import date

import pytest

from nzstats.cli import main
from nzstats.research import purge
from nzstats.research.manual_import import import_document
from nzstats.research.registry import load_registry
from nzstats.research.table_ingest import extract_version_tables
from nzstats.research.table_store import load_forecasts, load_rejections
from nzstats.sources.artifacts import ArtifactStore

from .conftest import NOW
from .llm_support import seed_version
from .pdf_table_support import table_pdf
from .support import BASE, institution
from .test_table_forecast import line, page

SENTINEL = "ZEBRAFISH-QUOKKA-7731"
URL = f"{BASE}/research/outlook-2026.pdf"
APPROVED = {
    "review_status": "needs_review", "approved_by": None, "approved_on": None, "approval_note": None,
    "manual_import": "approved", "manual_import_approved_by": "Test Owner",
    "manual_import_approved_on": "2026-10-28", "manual_import_note": "synthetic: terms permit a stored copy",
    "min_text_chars": 20,
}  # fmt: skip


def report_pdf(label: str = "OCR (%)") -> bytes:
    rows = [
        *line(686, label, ["4.25", "3.75", "3.25", "3.00"]),
        *line(672, "Annual CPI inflation (%)", ["4", "3", "2.6", "2.2"]),
    ]
    return table_pdf([page(rows, extra=[(72, 650, "Source: Example Research")])])


@pytest.fixture()
def artifacts(tmp_path):
    return ArtifactStore(tmp_path / "raw")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("table extraction must not use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)


def imported(conn, artifacts, body=None, **overrides):
    inst = institution(**{**APPROVED, **overrides})
    result = import_document(
        conn, inst, body=body or report_pdf(), file_format="pdf", url=URL, importer="Test Owner",
        note="saved from a browser", now=NOW, artifacts=artifacts, published_on=date(2026, 10, 1),
    )  # fmt: skip
    return {inst.key: inst}, result.version_id


def test_a_stored_pdf_yields_figures_and_a_rerun_is_unchanged(conn, artifacts):
    registry, v = imported(conn, artifacts)
    first = extract_version_tables(conn, v, artifacts, registry, NOW, isolate=False)
    assert (first.status, first.reason) == ("stored", None) and first.forecasts == 8
    again = extract_version_tables(conn, v, artifacts, registry, NOW, isolate=False)
    assert again.status == "unchanged" and again.forecasts == 8
    figures = {
        (f.indicator, f.horizon, str(f.value))
        for f in load_forecasts(conn, v)
        if f.kind == "forecast"
    }
    assert ("cpi_inflation", "year to June 2026", "2.6") in figures and (
        "ocr",
        "June 2026 quarter",
        "3.25",
    ) in figures


def test_reextracting_legacy_words_stores_current_interpretation(conn, artifacts):
    from nzstats.research.extract import ExtractionLimits
    from nzstats.research.table_store import store_extraction
    from nzstats.research.table_words import extract_words, words_sha256

    body = report_pdf()
    registry, v = imported(conn, artifacts, body)
    words = extract_words(body, ExtractionLimits(), isolate=False)
    store_extraction(
        conn, v, NOW, [], [], words_sha256=words_sha256(words), interpreter_version="tables-6"
    )
    result = extract_version_tables(conn, v, artifacts, registry, NOW, isolate=False)
    assert result.status == "stored"
    assert {f.interpreter_version for f in load_forecasts(conn, v)} == {"tables-7"}


def test_a_dry_run_reads_and_counts_but_writes_nothing(conn, artifacts):
    registry, v = imported(conn, artifacts)
    result = extract_version_tables(conn, v, artifacts, registry, NOW, dry_run=True, isolate=False)
    assert result.status == "dry_run" and result.forecasts == 8
    assert conn.execute("SELECT COUNT(*) FROM research_table_extraction").fetchone()[0] == 0


def test_rejections_are_stored_with_codes_only(conn, artifacts):
    body = table_pdf(
        [page(line(686, "Current account balance (% of GDP)", ["-6", "-5", "-4", "-3"]))]
    )
    registry, v = imported(conn, artifacts, body)
    result = extract_version_tables(conn, v, artifacts, registry, NOW, isolate=False)
    assert (result.status, result.forecasts, result.rejections) == ("stored", 0, 1)
    assert [r.code for r in load_rejections(conn, v)] == ["unmapped_row"]


def test_a_source_whose_route_is_not_permitted_is_refused(conn, artifacts):
    registry, v = imported(conn, artifacts)
    denied = institution(**{**APPROVED, "manual_import": "denied", "manual_import_approved_by": None,
                            "manual_import_approved_on": None, "manual_import_note": None})  # fmt: skip
    result = extract_version_tables(conn, v, artifacts, {denied.key: denied}, NOW, isolate=False)
    assert (result.status, result.reason) == ("refused", "source not permitted")
    assert conn.execute("SELECT COUNT(*) FROM research_table_extraction").fetchone()[0] == 0


def test_a_source_that_may_not_show_full_text_is_refused(conn, artifacts):
    version = seed_version(conn)  # held through the (approved) crawler route
    registry = {"example": institution(content_policy="metadata_only", min_text_chars=20)}
    result = extract_version_tables(conn, version, artifacts, registry, NOW, isolate=False)
    assert (result.status, result.reason) == ("refused", "content policy does not allow full text")


def test_only_a_pdf_version_is_read(conn, artifacts):
    version = seed_version(conn)  # stored as html text, no raw file
    registry = {"example": institution(min_text_chars=20)}
    result = extract_version_tables(conn, version, artifacts, registry, NOW, isolate=False)
    assert result.status == "refused" and result.reason in ("not a pdf", "raw copy unavailable")


def test_unknown_version_and_unknown_institution_are_refused(conn, artifacts):
    registry, v = imported(conn, artifacts)
    assert (
        extract_version_tables(conn, 999, artifacts, registry, NOW, isolate=False).reason
        == "unknown version"
    )
    assert (
        extract_version_tables(conn, v, artifacts, {}, NOW, isolate=False).reason
        == "unknown institution"
    )


def test_a_raw_copy_that_no_longer_matches_the_version_is_refused(conn, artifacts):
    registry, v = imported(conn, artifacts)
    rel = conn.execute("SELECT path FROM raw_artifact").fetchone()[0]
    (artifacts.root / rel).write_bytes(
        table_pdf([[]])
    )  # the stored bytes no longer match the version
    result = extract_version_tables(conn, v, artifacts, registry, NOW, isolate=False)
    assert (
        result.status == "refused" and result.reason == "raw copy does not match the stored version"
    )


def test_a_purged_version_is_refused(conn, artifacts, tmp_path):
    registry, v = imported(conn, artifacts)
    plan = purge.plan_purge(conn, "example", version_ids=[v])
    purge.apply_purge(
        conn, plan, artifacts, reason="takedown", purged_by="Owner", note="test", now=NOW
    )
    assert (
        extract_version_tables(conn, v, artifacts, registry, NOW, isolate=False).reason == "purged"
    )


def test_no_real_bank_can_be_extracted(conn, artifacts):
    registry = load_registry()
    for key in ("anz", "asb", "bnz", "westpac", "kiwibank"):
        v = seed_version(conn, key=key, doc=key)
        result = extract_version_tables(conn, v, artifacts, registry, NOW, isolate=False)
        assert (result.status, result.reason) == ("refused", "source not permitted"), key


REGISTRY = """
[institutions.banky]
name = "Banky"
kind = "bank"
allowed_hosts = ["banky.example.org"]
categories = ["economic_outlook"]
review_status = "needs_review"
content_policy = "full_text"
terms_evidence = "direct"
licence = "Synthetic test licence"
min_text_chars = 20
manual_import = "approved"
manual_import_approved_by = "Test Owner"
manual_import_approved_on = "2026-10-28"
manual_import_note = "synthetic: copies obtained by a person may be stored"
"""


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    path = tmp_path / "research.toml"
    path.write_text(textwrap.dedent(REGISTRY), encoding="utf-8")
    monkeypatch.setenv("NZSTATS_RESEARCH_SOURCES_FILE", str(path))
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    doc = tmp_path / "outlook.pdf"
    doc.write_bytes(report_pdf(f"OCR (%) {SENTINEL}"))
    return doc


def test_the_commands_import_extract_and_show_without_printing_any_text(cli, capsys):
    assert main(["research", "import", "banky", str(cli), "--url", "https://banky.example.org/o.pdf",
                 "--importer", "Owner", "--note", "n"]) == 0  # fmt: skip
    assert main(["research", "tables", "extract", "1", "--dry-run"]) == 0
    assert main(["research", "tables", "extract", "1"]) == 0
    assert main(["research", "tables", "extract", "1"]) == 0
    assert main(["research", "tables", "show", "1", "--json"]) == 0
    out = capsys.readouterr().out
    assert SENTINEL not in out and "Annual CPI" not in out
    data = json.loads(out[out.index("{") :])
    assert data["forecasts"] and {
        "indicator",
        "horizon",
        "kind",
        "unit",
        "value",
        "missing",
        "page",
        "table",
        "row",
        "col",
    } <= set(data["forecasts"][0])
    assert "label" not in data["forecasts"][0] and "raw_text" not in data["forecasts"][0]


def test_the_command_refuses_a_real_bank_version(cli, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NZSTATS_RESEARCH_SOURCES_FILE", raising=False)
    from nzstats.store.db import connect, migrate

    conn = connect(tmp_path / "data" / "nzstats.db")
    migrate(conn)
    v = seed_version(conn, key="anz", doc="a")
    conn.close()
    assert main(["research", "tables", "extract", str(v)]) == 1
    assert "refused (source not permitted)" in capsys.readouterr().out


def test_a_purge_that_lands_during_the_parse_is_refused_cleanly_and_stores_nothing(
    conn, artifacts, monkeypatch
):
    from nzstats.research import table_ingest

    registry, v = imported(conn, artifacts)
    real = table_ingest.extract_words

    def purge_meanwhile(*args, **kwargs):
        plan = purge.plan_purge(conn, "example", version_ids=[v])
        purge.apply_purge(
            conn, plan, artifacts, reason="takedown", purged_by="Owner", note="test", now=NOW
        )
        return real(*args, **kwargs)

    monkeypatch.setattr(table_ingest, "extract_words", purge_meanwhile)
    # the raw copy is gone with the purge, so the run ends in a fixed refusal, never an unhandled database error
    result = extract_version_tables(conn, v, artifacts, registry, NOW, isolate=False)
    assert (result.status, result.reason) in {
        ("refused", "purged"),
        ("refused", "raw copy unavailable"),
    }
    assert conn.execute("SELECT COUNT(*) FROM research_table_forecast").fetchone()[0] == 0

"""Phase 4AF: a clean, offline, end-to-end replay from SYNTHETIC PDF forecast tables to the internal routes.

Synthetic PDFs are imported by the real manual-import path under a synthetic registry, their tables are read by the
deterministic extractor, two of the reports are also summarised by a scripted local stand-in (the real pipeline and
verifier), and everything is read back through the internal bank routes. No bank is contacted, no hosted model is
called, nothing is paid for, and the whole replay is run twice from scratch to show it is deterministic. Real bank
keys are checked to stay permission-denied throughout."""

import json
import re
import socket
from datetime import date
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.cli import main
from nzstats.config import load_settings
from nzstats.research import fetch, providers
from nzstats.research.contract import LlmLimits
from nzstats.research.drafts_api import internal_drafts_router
from nzstats.research.manual_import import import_document
from nzstats.research.providers import Pricing
from nzstats.research.registry import load_registry
from nzstats.research.summarise import summarise_versions
from nzstats.research.table_ingest import extract_version_tables
from nzstats.research.table_store import load_forecasts, load_rejections
from nzstats.runtime import build_runtime
from nzstats.sources.artifacts import ArtifactStore
from tests.cpi_support import ingest_cpi
from tests.support import BASE as STATS_BASE

from .bank_support import BANK_KEYS, SYNTH_ADAPTERS, synthetic_registry
from .conftest import NOW
from .pdf_table_support import table_pdf
from .support import HOST
from .test_bank_e2e import FILLER, LOCAL, ROUTES, LocalStandIn
from .test_table_forecast import GROUPS, HEAD, line

PUBLISHED = {"q3": date(2026, 2, 10), "q4": date(2026, 5, 12)}
# bank -> report -> (OCR for June 2026, CPI for June 2026, CPI for September 2026 or "-", the figure its PROSE states)
REPORTS = {
    "bank_a": {"q3": ("3.50", "3.8", "3.5", "3.8"), "q4": ("3.25", "4.0", "3.6", "4.0")},
    "bank_b": {"q3": ("3.50", "3.9", "-", "3.9"), "q4": ("3.25", "4.2", "3.7", "4.2")},
    "bank_c": {"q3": ("3.75", "3.7", "3.4", "3.7"), "q4": ("3.50", "4.3", "3.8", "4.4")},  # prose disagrees with its table
}  # fmt: skip
SUMMARISED = (("bank_b", "q4"), ("bank_c", "q4"))


def report_pdf(bank: str, which: str) -> bytes:
    ocr, cpi, sep, prose = REPORTS[bank][which]
    page1 = [
        (72, 745, "Table 1: Forecasts (SYNTHETIC FIXTURE)"),
        *GROUPS,
        *line(700, "", HEAD),
        *line(686, "OCR (%)", ["4.25", "3.75", ocr, "3.00"]),
        *line(672, "Annual CPI inflation (%)", ["4.0", "3.1", cpi, sep]),
        (72, 650, f"Source: Example Bank {bank[-1].upper()}"),
    ]
    # The commentary sits on its own page, as in many reports: beside a table, the header's other periods make the
    # horizon of a sentence ambiguous to the model-claim verifier (verify-5), which is correct and conservative.
    pages = [
        page1,
        [
            (
                72,
                745,
                f"Annual CPI inflation is forecast to fall to {prose}% in the year to June 2026.",
            ),
            *[(72, 720 - 14 * i, FILLER) for i in range(6)],
        ],
    ]
    if (bank, which) == (
        "bank_a",
        "q4",
    ):  # a further table whose second row sits between two columns: refused whole
        shifted = [x + 30 for x in (250.0, 310.0, 370.0, 430.0)]
        pages.append([
            (72, 745, "Table 2: Revised forecasts (SYNTHETIC FIXTURE)"),
            *line(700, "", ["Dec-26", "Mar-27", "Jun-27", "Sep-27"]),
            *line(686, "OCR (%)", ["3", "3", "3", "3"]),
            *line(672, "Annual CPI inflation (%)", ["9.9", "9.9", "9.9", "9.9"], shifted),
        ])  # fmt: skip
    return table_pdf(pages)


def scripted(request) -> str:
    section = next(s for s in request.sections if "forecast to fall to" in s.text)
    stated = float(re.search(r"fall to ([0-9.]+)%", section.text).group(1))
    ref = {"version_id": request.version_id, "section_ordinal": section.ordinal}
    return json.dumps({
        "outlook": {"text": "Inflation is expected to ease.", "evidence": [
            {**ref, "quote": f"Annual CPI inflation is forecast to fall to {stated}%"}]},
        "indicators": ["cpi_inflation"],
        "forecasts": [{
            "indicator": "cpi_inflation", "indicator_label": "Annual CPI inflation",
            "horizon": "year to June 2026", "value": stated, "unit": "percent", "direction": "down",
            "issuer": request.author or "Example institution", "issuer_role": "author",
            "evidence": [{**ref, "quote": f"forecast to fall to {stated}% in the year to June 2026"}],
        }],
    })  # fmt: skip


def replay(data_dir: Path, site, monkeypatch):
    settings = load_settings({"NZSTATS_DATA_DIR": str(data_dir), "NZSTATS_BASE_URL": STATS_BASE})
    rt = build_runtime(settings, fetcher=site.fetcher())
    conn = rt.conn
    ingest_cpi(rt, site, "2025-12", "2026-03", "2026-06", "2026-09")
    conn.execute(
        "UPDATE vintage SET captured_at = (SELECT published_at FROM release WHERE id = release_id)"
    )
    registry = synthetic_registry()
    artifacts = ArtifactStore(settings.raw_dir)
    versions: dict[tuple[str, str], int] = {}
    for bank, reports in REPORTS.items():
        for which in reports:
            result = import_document(
                conn, registry[bank], body=report_pdf(bank, which), file_format="pdf",
                url=f"https://{HOST}/research/outlook/{bank}-{which}", importer="Test Importer",
                note="synthetic fixture", now=NOW, artifacts=artifacts, title=f"Example {bank} {which}",
                published_on=PUBLISHED[which],
            )  # fmt: skip
            assert result.outcome == "new", (bank, which, result)
            versions[(bank, which)] = result.version_id
    for v in versions.values():
        assert extract_version_tables(conn, v, artifacts, registry, NOW).status == "stored"
    provider = LocalStandIn(scripted, model="local-1", hosted=False)
    done = summarise_versions(
        conn, registry, provider, pricing=Pricing(0.0, 0.0), limits=LlmLimits(max_documents_per_run=10),
        now_fn=lambda: NOW, sleep=lambda _s: None, version_ids=[versions[k] for k in SUMMARISED],
    )  # fmt: skip
    assert done.counts.get("verified", 0) + done.counts.get("failed_verification", 0) == 2
    (data_dir / "internal-drafts.json").write_text(json.dumps({"auto_display": {
        "enabled": True, "enabled_by": "Test Owner", "enabled_on": "2026-11-10", "note": "synthetic"}}))  # fmt: skip
    monkeypatch.setattr("nzstats.research.bank_api.utc_now", lambda: NOW)
    calls = len(provider.calls)

    def app(reg):
        return TestClient(create_app(settings, routers=[
            internal_drafts_router(enabled=True, registry=lambda: reg, bank_adapters=SYNTH_ADAPTERS)]))  # fmt: skip

    client = app(registry)
    out = {
        r: client.get(f"/api/internal/bank-intelligence/{r}", headers=LOCAL).text for r in ROUTES
    }
    real = app(load_registry()).get("/api/internal/bank-intelligence/summary", headers=LOCAL).json()
    assert len(provider.calls) == calls  # reading the routes called no model
    stored = {k: ([(f.indicator, f.horizon, f.kind, str(f.value), f.missing) for f in load_forecasts(conn, v)],
                  [r.code for r in load_rejections(conn, v)]) for k, v in versions.items()}  # fmt: skip
    return out, provider, {"real_summary": real, "versions": versions, "stored": stored}


def guards(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("the replay must make no hosted-model call and no network request")

    monkeypatch.setattr(providers, "build_provider", boom)
    monkeypatch.setattr(fetch.ResearchFetcher, "__init__", boom)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)


def by_method(body):
    return {(f["forecast"]["institution"]["key"], f["forecast"]["published_on"], f["forecast"]["indicator"],
             f["forecast"]["horizon"], f["extraction_method"]): f["forecast"]["value"] for f in body["forecasts"]}  # fmt: skip


def test_offline_replay_from_pdf_tables_to_the_internal_routes(site, tmp_path, monkeypatch):
    guards(monkeypatch)
    first, provider, extra = replay(tmp_path / "one", site, monkeypatch)
    assert (
        len(provider.calls) == 2 and provider.hosted is False
    )  # only the two reports chosen for a model reading

    # What the tables yielded: figures for the forecast columns, actuals kept apart, the dash kept as missing.
    stored = extra["stored"]
    q3_b = stored[("bank_b", "q3")][0]
    assert ("cpi_inflation", "year to September 2026", "forecast", "None", True) in q3_b
    assert ("cpi_inflation", "year to June 2026", "forecast", "3.9", False) in q3_b
    assert ("cpi_inflation", "year to December 2025", "actual", "4.0", False) in q3_b
    # The shifted second table was refused whole: no figure from it, one fixed rejection code.
    assert stored[("bank_a", "q4")][1] == ["ambiguous_columns"]
    assert not any(v == "9.9" for rows in stored.values() for *_, v, _m in rows[0])

    forecasts = json.loads(first["forecasts"])
    shown = by_method(forecasts)
    # Table figures reach the analytics; the two bank-B readings of the same number are one statement (table kept).
    assert shown[("bank_a", "2026-05-12", "cpi_inflation", "year to June 2026", "table")] == 4.0
    assert (
        shown[
            (
                "bank_b",
                "2026-05-12",
                "cpi_inflation",
                "year to June 2026",
                "table",
            )
        ]
        == 4.2
    )
    assert not any(
        k[3] == "year to September 2026" and k[0] == "bank_b" and k[1] == "2026-02-10"
        for k in shown
    )  # missing stays missing
    assert 9.9 not in shown.values()
    assert (
        forecasts["table_reconciliation"]["exact_match"] == 1
        and forecasts["table_reconciliation"]["contradictory_value"] == 1
    )
    codes = sorted((e["institution_key"], e["code"]) for e in forecasts["excluded"])
    assert ("bank_c", "conflicting_forecasts") in codes and (
        "bank_c",
        "newer_claim_unusable",
    ) in codes

    consensus = json.loads(first["consensus"])["consensus"]
    groups = {(g["indicator"], g["horizon_label"]): g for g in consensus["groups"]}
    cpi, ocr = groups[("cpi_inflation", "Year to June 2026")], groups[("ocr", "June 2026 quarter")]
    sept = groups[("cpi_inflation", "Year to September 2026")]
    assert {c["key"]: c["value"] for c in cpi["contributors"]} == {"bank_a": 4.0, "bank_b": 4.2}
    assert cpi["title"] == "Two-bank comparison" and cpi["disclaimer"] == "Not a market consensus."
    assert {c["key"]: c["value"] for c in ocr["contributors"]} == {
        "bank_a": 3.25,
        "bank_b": 3.25,
        "bank_c": 3.5,
    }
    assert ocr["title"] == "Consensus of banks" and ocr["median"] == 3.25
    # bank C's disagreement is about the June figure only: its September table figure stands, so three banks are compared.
    assert {c["key"]: c["value"] for c in sept["contributors"]} == {
        "bank_a": 3.6,
        "bank_b": 3.7,
        "bank_c": 3.8,
    }

    revisions = json.loads(first["revisions"])["histories"]
    series = [
        s for h in revisions for s in h["history"]["series"] if s["institution"]["key"] == "bank_a"
    ]
    cpi_a = next(s for s in series if s["indicator"] == "cpi_inflation")
    assert [v["value"] for v in cpi_a["vintages"]] == [
        3.8,
        4.0,
    ]  # revision between two table-read reports

    evaluation = json.loads(first["evaluation"])
    assert any(
        e["status"] == "matched" and e["first"]["value"] == 4.1 for e in evaluation["evaluated"]
    )

    # Real banks stay permission-denied, and nothing about them reaches the page.
    real = extra["real_summary"]["cards"]
    assert sorted(c["key"] for c in real) == sorted(BANK_KEYS)
    assert {c["state"] for c in real} == {"permission_denied"} and all(
        c["stance"] is None for c in real
    )

    # Deterministic: a second replay from an empty directory gives byte-identical answers.
    second, provider2, extra2 = replay(tmp_path / "two", site, monkeypatch)
    assert second == first and len(provider2.calls) == 2 and extra2["stored"] == extra["stored"]


def test_the_command_line_shows_the_same_stored_figures_without_text(
    site, tmp_path, monkeypatch, capsys
):
    guards(monkeypatch)
    _, _, extra = replay(tmp_path / "cli", site, monkeypatch)
    v = extra["versions"][("bank_a", "q4")]
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "cli"))
    capsys.readouterr()
    assert (
        main(["research", "tables", "show", str(v), "--json"]) == 1
    )  # the real registry refuses a synthetic bank
    assert "refused (unknown institution)" in capsys.readouterr().out

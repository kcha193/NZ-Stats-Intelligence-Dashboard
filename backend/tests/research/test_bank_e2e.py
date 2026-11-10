"""Phase 4AE: a clean, offline, end-to-end replay with SYNTHETIC bank documents.

Synthetic documents are imported by the real manual-import path under a synthetic registry, summarised through the
real summarise pipeline by a scripted local stand-in for a model, and read back through the internal routes. No bank
is contacted, no hosted model is called, nothing is paid for, and the whole replay is run twice from scratch to show
it is deterministic. Real bank keys are checked to stay permission-denied throughout."""

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.config import load_settings
from nzstats.research import fetch, providers
from nzstats.research.contract import LlmLimits, ProviderResponse
from nzstats.research.drafts_api import internal_drafts_router
from nzstats.research.manual_import import import_document
from nzstats.research.private_api import CLIENT_HEADER
from nzstats.research.providers import FakeProvider, Pricing
from nzstats.research.registry import load_registry
from nzstats.research.summarise import summarise_versions
from nzstats.runtime import build_runtime
from tests.cpi_support import ingest_cpi
from tests.support import BASE as STATS_BASE

from .bank_support import BANK_KEYS, SYNTH_ADAPTERS, synthetic_registry
from .support import HOST

NOW = datetime(2026, 11, 10, 1, 0, tzinfo=UTC)
LOCAL = {"host": "127.0.0.1:8000", CLIENT_HEADER: "dashboard"}
ROUTES = ("summary", "forecasts", "revisions", "consensus", "evaluation", "freshness")
FILLER = "The example economy is assumed to grow slowly in this synthetic fixture text. "
WRONG = 9.9  # what the scripted model claims for bank_b's second report; its text says 4.2
# bank -> [(path, published, value stated in the text)]
DOCS = {
    "bank_a": [("q3", date(2026, 2, 10), 3.8), ("q4", date(2026, 5, 12), 4.0)],
    "bank_b": [("q3", date(2026, 2, 11), 3.9), ("q4", date(2026, 5, 13), 4.2)],
    "bank_c": [("q3", date(2026, 2, 12), 3.7), ("q4", date(2026, 5, 14), 4.3)],
    "ref_central": [("mps", date(2026, 5, 20), 4.05)],
}


class LocalStandIn(FakeProvider):
    """A scripted stand-in for a local model: named like one so the draft gate treats it as a reviewed local route."""

    name = "openai_compatible"

    def summarise(self, request):
        r = super().summarise(request)
        return ProviderResponse(r.text, r.model, r.input_tokens, r.output_tokens, "stop")


def html(bank: str, path: str, value: float) -> bytes:
    return (
        f"<html><head><title>Example {bank} {path}</title></head><body><main><h1>{bank} {path}</h1>"
        f"<h2>Inflation</h2><p>{FILLER * 3} Annual CPI inflation is forecast to fall to {value}% in the year to"
        f" June 2026.</p><h2>Risks</h2><p>{FILLER * 2}</p></main></body></html>"
    ).encode()


def scripted(wrong_versions: set[int]):
    def respond(request) -> str:
        section = next(s for s in request.sections if "Annual CPI inflation" in s.text)
        stated = float(re.search(r"fall to ([0-9.]+)%", section.text).group(1))
        claimed = WRONG if request.version_id in wrong_versions else stated
        ref = {"version_id": request.version_id, "section_ordinal": section.ordinal}
        return json.dumps({
            "outlook": {"text": "Inflation is expected to ease.", "evidence": [
                {**ref, "quote": f"Annual CPI inflation is forecast to fall to {stated}%"}]},
            "indicators": ["cpi_inflation"],
            "forecasts": [{
                "indicator": "cpi_inflation", "indicator_label": "Annual CPI inflation",
                "horizon": "year to June 2026", "value": claimed, "unit": "percent", "direction": "down",
                "issuer": request.author or "Example institution", "issuer_role": "author",
                "evidence": [{**ref, "quote": f"forecast to fall to {stated}% in the year to June 2026"}],
            }],
        })  # fmt: skip

    return respond


def replay(data_dir: Path, site, monkeypatch) -> tuple[dict[str, str], LocalStandIn, dict]:
    settings = load_settings({"NZSTATS_DATA_DIR": str(data_dir), "NZSTATS_BASE_URL": STATS_BASE})
    rt = build_runtime(settings, fetcher=site.fetcher())
    conn = rt.conn
    ingest_cpi(rt, site, "2025-12", "2026-03", "2026-06", "2026-09")
    conn.execute(
        "UPDATE vintage SET captured_at = (SELECT published_at FROM release WHERE id = release_id)"
    )
    registry = synthetic_registry()
    versions: dict[tuple[str, str], int] = {}
    for bank, docs in DOCS.items():
        for path, published, value in docs:
            result = import_document(
                conn, registry[bank], body=html(bank, path, value), file_format="html",
                url=f"https://{HOST}/research/outlook/{bank}-{path}", importer="Test Importer",
                note="synthetic fixture", now=NOW, artifacts=None, title=f"Example {bank} {path}",
                published_on=published,
            )  # fmt: skip
            assert result.outcome == "new", (bank, path, result)
            versions[(bank, path)] = result.version_id
    provider = LocalStandIn(scripted({versions[("bank_b", "q4")]}), model="local-1", hosted=False)
    done = summarise_versions(
        conn, registry, provider, pricing=Pricing(0.0, 0.0), limits=LlmLimits(max_documents_per_run=10), now_fn=lambda: NOW,
        sleep=lambda _s: None,
    )  # fmt: skip
    assert done.counts.get("verified", 0) + done.counts.get("failed_verification", 0) == 7
    (data_dir / "internal-drafts.json").write_text(json.dumps({"auto_display": {
        "enabled": True, "enabled_by": "Test Owner", "enabled_on": "2026-11-10", "note": "synthetic"}}))  # fmt: skip
    monkeypatch.setattr("nzstats.research.bank_api.utc_now", lambda: NOW)
    calls_after_summarise = len(provider.calls)

    def app(reg):
        return TestClient(create_app(settings, routers=[
            internal_drafts_router(enabled=True, registry=lambda: reg, bank_adapters=SYNTH_ADAPTERS)]))  # fmt: skip

    client = app(registry)
    out = {
        r: client.get(f"/api/internal/bank-intelligence/{r}", headers=LOCAL).text for r in ROUTES
    }
    real = app(load_registry())
    real_summary = real.get("/api/internal/bank-intelligence/summary", headers=LOCAL).json()
    assert len(provider.calls) == calls_after_summarise  # reading the routes called no model
    return out, provider, {"real_summary": real_summary, "versions": versions}


def test_offline_replay(site, tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("the replay must make no hosted-model call and no network request")

    monkeypatch.setattr(providers, "build_provider", boom)
    monkeypatch.setattr(fetch.ResearchFetcher, "__init__", boom)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", boom)

    first, provider, extra = replay(tmp_path / "one", site, monkeypatch)
    assert len(provider.calls) == 7  # one scripted local call per imported report, and no others
    assert provider.hosted is False

    forecasts = json.loads(first["forecasts"])
    kept = {(f["forecast"]["institution"]["key"], f["forecast"]["published_on"]): f["forecast"]["value"]
            for f in forecasts["forecasts"]}  # fmt: skip
    assert kept[("bank_a", "2026-05-12")] == 4.0 and kept[("bank_c", "2026-05-14")] == 4.3
    assert ("bank_b", "2026-05-13") not in kept and WRONG not in kept.values()
    assert [(e["institution_key"], e["code"]) for e in forecasts["excluded"]] == [
        ("bank_b", "claim_failed_checks")
    ]

    consensus = json.loads(first["consensus"])["consensus"]
    (group,) = consensus["groups"]
    values = {c["key"]: (c["value"], c["published_on"]) for c in group["contributors"]}
    assert values == {  # bank_b's failed latest claim never counts; its earlier clean report stands, dated
        "bank_a": (4.0, "2026-05-12"), "bank_b": (3.9, "2026-02-11"), "bank_c": (4.3, "2026-05-14"),
    }  # fmt: skip
    assert (
        group["title"] == "Consensus of banks" and group["disclaimer"] == "Not a market consensus."
    )
    assert [m["key"] for m in group["markers"]] == ["ref_central"]
    assert WRONG not in [c["value"] for c in group["contributors"]]

    revisions = json.loads(first["revisions"])["histories"]
    a = next(
        s for h in revisions for s in h["history"]["series"] if s["institution"]["key"] == "bank_a"
    )
    assert [v["value"] for v in a["vintages"]] == [3.8, 4.0]
    assert a["vintages"][-1]["revision"] == 0.2 or abs(a["vintages"][-1]["revision"] - 0.2) < 1e-9

    evaluation = json.loads(first["evaluation"])
    matched = [e for e in evaluation["evaluated"] if e["status"] == "matched"]
    assert matched and all(
        e["first"]["value"] == 4.1 for e in matched
    )  # the first-published June 2026 actual
    assert WRONG not in [e["forecast"]["value"] for e in evaluation["evaluated"]]

    freshness = json.loads(first["freshness"])["banks"]
    assert {b["key"]: b["state"] for b in freshness} == dict.fromkeys(
        ("bank_a", "bank_b", "bank_c"), "missing"
    )
    for bank in (
        freshness
    ):  # the outlook series is stale (last report over 100 days old); no weekly was ever received
        assert {s["series_key"]: s["state"] for s in bank["series"]} == {
            "outlook": "stale",
            "weekly": "missing",
        }

    real = extra["real_summary"]["cards"]
    assert sorted(c["key"] for c in real) == sorted(BANK_KEYS)
    assert {c["state"] for c in real} == {"permission_denied"} and all(
        c["stance"] is None for c in real
    )

    # Deterministic: a second replay from an empty directory gives byte-identical route answers.
    second, provider2, _ = replay(tmp_path / "two", site, monkeypatch)
    assert second == first and len(provider2.calls) == 7

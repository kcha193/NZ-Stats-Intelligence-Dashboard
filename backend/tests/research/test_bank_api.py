"""Phase 4AE: the internal bank-intelligence routes. Off by default, local dashboard only, read-only, an allowlisted
response, and no provider or fetch on any read (SYNTHETIC FIXTURE)."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from nzstats.research import fetch, providers
from nzstats.research.drafts_api import internal_drafts_router
from nzstats.research.private_api import CLIENT_HEADER
from nzstats.research.registry import RegistryError, load_registry

from .bank_support import BANK_KEYS, SYNTH_ADAPTERS, synthetic_registry
from .llm_support import SECTIONS, draft, seed_version
from .test_drafts_auto import RAW, store_hosted

NOW = datetime(2026, 11, 10, 1, 0, tzinfo=UTC)
LOCAL = {"host": "127.0.0.1:8000", CLIENT_HEADER: "dashboard"}
BASE = "/api/internal/bank-intelligence"
ROUTES = ("summary", "forecasts", "revisions", "consensus", "evaluation", "freshness")
AUTO_FILE = {
    "auto_display": {
        "enabled": True,
        "enabled_by": "Test Owner",
        "enabled_on": "2026-11-10",
        "note": "OWNER NOTE",
    }
}
PRIVATE_TEXT = (RAW, "raw_output", "output_sha256", "parameters", "temperature", "cost_usd",
                "Test Owner", "OWNER NOTE", SECTIONS[0])  # fmt: skip


def bank_doc(conn, key, cpi, *, doc="research/outlook/q4", published_on="2026-10-01", claimed=None):
    """A bank report whose text says `cpi`; `claimed` makes the stored claim state a different (unsupported) value."""
    sections = (SECTIONS[0], SECTIONS[1].replace("2.1%", f"{cpi}%"))
    v = seed_version(conn, sections, key=key, doc=doc, published_on=published_on)
    out = draft(v)
    out["forecasts"][1]["value"] = cpi if claimed is None else claimed
    out["forecasts"][1]["evidence"][0]["quote"] = (
        f"forecast to fall to {cpi}% in the year to June 2027"
    )
    out["outlook"]["evidence"][1]["quote"] = f"Annual CPI inflation is forecast to fall to {cpi}%"
    return store_hosted(conn, v, output=out)


@pytest.fixture()
def bank_app(make, tmp_path, monkeypatch):
    build, conn = make
    monkeypatch.setattr("nzstats.research.bank_api.utc_now", lambda: NOW)
    (tmp_path / "data" / "internal-drafts.json").write_text(json.dumps(AUTO_FILE))
    bank_doc(conn, "bank_a", 2.0, doc="research/outlook/q3", published_on="2026-07-01")
    bank_doc(conn, "bank_a", 2.4)
    bank_doc(conn, "bank_b", 2.2)
    bank_doc(conn, "bank_c", 2.8)
    bank_doc(conn, "ref_central", 2.3)
    reg = synthetic_registry()

    def client(*, enabled=True, registry=None):
        loader = registry if registry is not None else (lambda: reg)
        return build(
            routers=[
                internal_drafts_router(
                    enabled=enabled, registry=loader, bank_adapters=SYNTH_ADAPTERS
                )
            ]
        )

    return client, conn


def get(client, route, **params):
    return client.get(f"{BASE}/{route}", headers=LOCAL, params=params)


def test_the_notice_is_the_draft_notice():
    from nzstats.research import bank_models, drafts_api

    assert bank_models.NOTICE == drafts_api.NOTICE


def test_off_unless_enabled_and_then_indistinguishable_from_an_unknown_path(bank_app):
    client, _ = bank_app
    off = client(enabled=False)
    unknown = off.get("/api/no-such-thing", headers=LOCAL)
    for route in ROUTES:
        r = get(off, route)
        assert (r.status_code, r.json()) == (404, unknown.json())


@pytest.mark.parametrize(
    "headers",
    [
        {"host": "127.0.0.1:8000"},
        {"host": "evil.example:8000", CLIENT_HEADER: "dashboard"},
        {**LOCAL, "origin": "http://evil.example"},
        {**LOCAL, "sec-fetch-site": "cross-site"},
        {**LOCAL, CLIENT_HEADER: "other"},
    ],
)
def test_only_the_local_dashboard_may_read(bank_app, headers):
    client, _ = bank_app
    for route in ROUTES:
        assert client().get(f"{BASE}/{route}", headers=headers).status_code == 403


def test_summary_cards_state_and_stance_label(bank_app):
    client, _ = bank_app
    r = get(client(), "summary")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"]
    cards = {c["key"]: c for c in r.json()["cards"]}
    assert sorted(cards) == ["bank_a", "bank_b", "bank_c"]
    a = cards["bank_a"]
    assert a["name"] == "Example Bank A" and a["published_on"] == "2026-10-01"
    assert a["state"] == "missing"  # the weekly series has nothing stored ...
    assert (
        a["worst_series"] == "Weekly Note"
    )  # ... and the card says which, beside the report it did receive
    assert a["stance"]["label"] == "AI interpretation" and a["stance"]["claim_status"] == "clean"
    assert "ref_central" not in cards
    assert "not independently reviewed" in r.json()["notice"].lower()


def test_forecasts_carry_lineage_and_kind(bank_app):
    client, _ = bank_app
    body = get(client(), "forecasts").json()
    cpi = [f for f in body["forecasts"] if f["forecast"]["indicator"] == "cpi_inflation"]
    assert {f["forecast"]["institution"]["key"] for f in cpi} == {"bank_a", "bank_b", "bank_c"}
    first = cpi[0]
    assert {
        "claim_path",
        "report_kind",
        "adjustment",
        "geography",
        "measure",
        "verifier_version",
    } <= set(first)
    assert first["report_kind"] == "outlook" and first["forecast"]["evidence"][0]["quote"]
    assert body["comparison"][0]["adjustment"] == "not_stated"
    assert {b["key"] for b in body["banks"]} == {"bank_a", "bank_b", "bank_c"}


def test_consensus_and_divergence(bank_app):
    client, _ = bank_app
    body = get(client(), "consensus").json()
    (group,) = [g for g in body["consensus"]["groups"] if g["indicator"] == "cpi_inflation"]
    assert group["n"] == 3 and group["title"] == "Consensus of banks"
    assert group["disclaimer"] == "Not a market consensus."
    assert {c["key"]: c["value"] for c in group["contributors"]} == {
        "bank_a": 2.4, "bank_b": 2.2, "bank_c": 2.8,
    }  # fmt: skip
    assert [m["key"] for m in group["markers"]] == ["ref_central"]
    (div,) = body["divergence"]
    assert div["spread"] == pytest.approx(0.6)
    assert (div["basis_label"], div["adjustment"]) == (group["basis_label"], group["adjustment"])


def test_what_was_left_out_and_why_reaches_the_reader_on_every_route(bank_app):
    client, conn = bank_app
    # bank_b's newest report has a claim that fails its checks; its older figure must not stand in for it.
    bank_doc(conn, "bank_b", 2.5, doc="research/outlook/q5", published_on="2026-10-20", claimed=9.9)
    c = client()
    forecasts = get(c, "forecasts").json()
    left_out = {(e["institution_key"], e["code"]) for e in forecasts["excluded"]}
    assert ("bank_b", "claim_failed_checks") in left_out
    assert ("bank_b", "newer_claim_unusable") in left_out
    assert all(e["reason"] for e in forecasts["excluded"])
    in_table = {
        r["forecast"]["institution"]["key"]
        for g in forecasts["comparison"][0]["comparison"]["groups"]
        if g["indicator"] == "cpi_inflation"
        for r in g["rows"]
    }
    assert in_table == {"bank_a", "bank_c"}  # a dash for bank_b, not its older 2.2
    consensus = get(c, "consensus").json()["consensus"]
    (group,) = [g for g in consensus["groups"] if g["indicator"] == "cpi_inflation"]
    assert {x["key"] for x in group["contributors"]} == {"bank_a", "bank_c"}
    assert group["title"] == "Two-bank comparison"
    assert ("bank_b", "newer_claim_unusable") in {
        (e["institution_key"], e["code"]) for e in consensus["excluded"]
    }
    revisions = get(c, "revisions").json()
    assert ("bank_b", "newer_claim_unusable") in {
        (e["institution_key"], e["code"]) for e in revisions["excluded"]
    }


def test_revisions_show_both_vintages(bank_app):
    client, _ = bank_app
    body = get(client(), "revisions").json()
    series = [s for h in body["histories"] for s in h["history"]["series"]]
    (a,) = [
        s
        for s in series
        if s["institution"]["key"] == "bank_a" and s["indicator"] == "cpi_inflation"
    ]
    assert [v["value"] for v in a["vintages"]] == [2.0, 2.4]


def test_evaluation_validates_the_indicator_and_answers_without_actuals(bank_app):
    client, _ = bank_app
    ok = get(client(), "evaluation", indicator="cpi_inflation")
    assert ok.status_code == 200 and ok.json()["indicator"] == "cpi_inflation"
    assert get(client(), "evaluation", indicator="Bad!").status_code == 422


def test_freshness_reports_series_states_and_auckland_dates(bank_app):
    client, _ = bank_app
    body = get(client(), "freshness").json()
    a = next(b for b in body["banks"] if b["key"] == "bank_a")
    assert {s["series_key"]: s["state"] for s in a["series"]} == {
        "outlook": "ok",
        "weekly": "missing",
    }
    outlook = next(s for s in a["series"] if s["series_key"] == "outlook")
    assert outlook["newest_published_on"] == "2026-10-01"
    assert outlook["ingested_at"].endswith("+13:00") or outlook["ingested_at"].endswith("+12:00")
    assert body["exit_code"] == 1


def test_no_route_leaks_private_fields(bank_app):
    client, _ = bank_app
    for route in ROUTES:
        text = get(client(), route).text
        for secret in PRIVATE_TEXT:
            assert secret not in text, (route, secret)


def test_the_real_registry_shows_every_bank_permission_denied_and_nothing_else(bank_app):
    client, _ = bank_app
    real = load_registry()
    c = client(registry=lambda: real)
    cards = {x["key"]: x for x in get(c, "summary").json()["cards"]}
    assert sorted(cards) == sorted(BANK_KEYS)
    assert {x["state"] for x in cards.values()} == {"permission_denied"}
    assert all(x["stance"] is None for x in cards.values())
    assert all(
        x["worst_series"] is None for x in cards.values()
    )  # a bank-wide state names no series
    assert get(c, "forecasts").json()["forecasts"] == []
    assert get(c, "consensus").json()["consensus"]["groups"] == []


def test_an_unreadable_registry_shows_nothing(bank_app):
    client, _ = bank_app

    def broken():
        raise RegistryError("boom")

    c = client(registry=broken)
    assert get(c, "summary").json()["cards"] == []
    assert get(c, "forecasts").json()["forecasts"] == []
    # An unreadable registry is "could not run", the code `bank-status` uses, not a clean bill of health.
    assert get(c, "freshness").json() == {"banks": [], "exit_code": 3}


def test_zero_provider_calls_and_fetches_on_every_route(bank_app, monkeypatch):
    client, conn = bank_app
    before = conn.execute("SELECT COUNT(*) FROM research_llm_usage").fetchone()[0]

    def boom(*_a, **_k):
        raise AssertionError("a bank read must not call a provider or fetch")

    monkeypatch.setattr(providers, "build_provider", boom)
    monkeypatch.setattr(fetch.ResearchFetcher, "__init__", boom)
    # The real network transports only: the TestClient's own in-process transport must keep working.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", boom)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", boom)
    c = client()
    for route in ROUTES:
        assert get(c, route).status_code == 200
    assert conn.execute("SELECT COUNT(*) FROM research_llm_usage").fetchone()[0] == before

"""Phase 3D-B routes: forecast history, evaluation and consensus. Same switch, same gate, no leaks (SYNTHETIC FIXTURE)."""

from __future__ import annotations

import json

import pytest

from .llm_support import seed_version
from .public_support import displayable, registry, store_summary
from .test_api import PRIVATE, _reg, _two_institutions

NEW = ("/api/research/forecast-history", "/api/research/forecast-evaluation?indicator=cpi_inflation",
       "/api/research/consensus")  # fmt: skip


def test_new_routes_are_off_unless_switched_on(make):
    build, conn = make
    _two_institutions(conn)
    client = build(enabled=False, reg=_reg())
    assert all(client.get(r).status_code == 404 for r in NEW)
    on = build(reg=_reg())
    assert all(on.get(r).status_code == 200 for r in NEW)


def test_responses_carry_no_private_fields_or_document_text(make):
    build, conn = make
    _two_institutions(conn)
    client = build(reg=_reg())
    for route in NEW:
        body = json.dumps(client.get(route).json())
        assert not [p for p in PRIVATE if p in body], route


def test_unpublished_and_unapproved_summaries_never_reach_history_or_consensus(make):
    build, conn = make
    _two_institutions(conn)
    hidden = seed_version(conn, key="alpha", doc="later", published_on="2026-10-01")
    store_summary(conn, hidden, review="approved", publish=False)  # approved but never published
    unreviewed = seed_version(conn, key="beta", doc="later", published_on="2026-10-02")
    store_summary(conn, unreviewed, review=None, publish=False)
    client = build(reg=_reg())
    history = client.get("/api/research/forecast-history").json()
    ids = {v["summary_id"] for s in history["series"] for v in s["vintages"]}
    assert ids == {1, 2}  # the two published summaries only
    consensus = client.get("/api/research/consensus").json()
    assert {c["summary_id"] for g in consensus["groups"] for c in g["contributors"]} <= {1, 2}


def test_history_groups_vintages_and_consensus_counts_institutions(make):
    build, conn = make
    _two_institutions(conn)
    client = build(reg=_reg())
    history = client.get("/api/research/forecast-history?indicator=cpi_inflation").json()
    assert {s["institution"]["key"] for s in history["series"]} == {"alpha", "beta"}
    assert all(s["indicator"] == "cpi_inflation" for s in history["series"])
    (cpi,) = [
        g for g in client.get("/api/research/consensus?indicator=cpi_inflation").json()["groups"]
    ]
    assert (
        cpi["n"] == 2
        and cpi["status"] == "available"
        and "not statistically calibrated" in cpi["note"]
    )


def test_link_only_and_revoked_sources_contribute_nothing(make):
    build, conn = make
    _two_institutions(conn)
    link_only = build(reg=_reg(alpha="link_only")).get("/api/research/forecast-history").json()
    assert {s["institution"]["key"] for s in link_only["series"]} == {"beta"}
    revoked = registry(displayable("alpha", level="none", public_display_approved_by=None,
                                   public_display_approved_on=None, public_display_note=None),
                       displayable("beta", level="summary"))  # fmt: skip
    body = build(reg=revoked).get("/api/research/consensus").json()
    assert all(c["key"] != "alpha" for g in body["groups"] for c in g["contributors"])


def test_evaluation_states_are_explicit(make):
    build, conn = make
    _two_institutions(conn)
    client = build(reg=_reg())
    ocr = client.get("/api/research/forecast-evaluation?indicator=ocr").json()
    assert ocr["state"] == "no_official_series" and ocr["evaluated"] == []
    assert "RBNZ" in ocr["unavailable_reason"] and ocr["actuals_as_of"] is None
    # Phase 4C: GDP is evaluated against official Stats NZ GDP; none is stored here, so nothing is matched.
    gdp = client.get("/api/research/forecast-evaluation?indicator=gdp").json()
    assert gdp["state"] in ("available", "nothing_to_evaluate") and gdp[
        "official_series"
    ].startswith("gdp.")
    assert all(e["status"] == "pending" for e in gdp["evaluated"])
    cpi = client.get("/api/research/forecast-evaluation?indicator=cpi_inflation").json()
    # No CPI release is stored in this database: the June 2027 forecasts are pending, never matched to another quarter.
    assert cpi["state"] == "available" and cpi["actuals_as_of"] is None
    assert {e["status"] for e in cpi["evaluated"]} == {"pending"}
    assert all(r["available"] is False for r in cpi["rankings"])
    nothing = build(reg=registry(displayable("gamma"))).get(
        "/api/research/forecast-evaluation?indicator=cpi_inflation"
    )
    assert nothing.json()["state"] == "nothing_to_evaluate"


@pytest.mark.parametrize(
    "query", ["indicator=../x", "indicator=" + "a" * 41, "institution=Bad Key"]
)
def test_bad_parameters_are_rejected(make, query):
    build, conn = make
    client = build(reg=_reg())
    assert client.get(f"/api/research/forecast-history?{query}").status_code == 422


def test_new_routes_are_read_only(make):
    build, conn = make
    client = build(reg=_reg())
    for route in NEW:
        path = route.split("?")[0]
        assert client.post(path).status_code == 405 and client.delete(path).status_code == 405

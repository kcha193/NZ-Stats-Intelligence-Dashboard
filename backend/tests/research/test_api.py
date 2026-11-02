"""The public research API (Phase 3C): disabled by default, read-only, and an allowlist of fields (SYNTHETIC FIXTURE)."""

import json

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.config import load_settings
from nzstats.research.registry import RegistryError

from .llm_support import NOW, SECTIONS, draft, seed_version
from .public_support import displayable, registry, store_summary

PRIVATE = ("RAW MODEL OUTPUT", "PRIVATE REVIEW NOTE", "Private Reviewer Name", "Private Approver",
           "PRIVATE PUBLICATION NOTE", "raw_output", "review_note", "reviewed_by", "parameters",
           "temperature", "input_sha256", "cost_usd", SECTIONS[0], SECTIONS[1])  # fmt: skip
ROUTES = ("/api/research/feed", "/api/research/forecasts", "/api/research/summaries/1")


def _two_institutions(conn):
    """alpha (excerpt) published 2026-08-13 and beta (summary) published 2026-09-01, each one summary."""
    a = seed_version(conn, key="alpha", doc="a", published_on="2026-08-13")
    b = seed_version(conn, key="beta", doc="b", published_on="2026-09-01")
    out = draft(b)
    out["outlook"]["text"] = "Inflation eases while growth recovers <script>alert('x')</script>."
    return store_summary(conn, a), store_summary(conn, b, output=out)


def _reg(alpha="excerpt", beta="summary"):
    return registry(displayable("alpha", level=alpha), displayable("beta", level=beta))


def test_every_route_is_disabled_by_default_and_indistinguishable_from_an_unknown_path(make):
    build, conn = make
    _two_institutions(conn)
    client = build(enabled=None, reg=_reg())  # NZSTATS_PUBLIC_RESEARCH is unset
    unknown = client.get("/api/no-such-thing")
    for route in ROUTES:
        r = client.get(route)
        assert (r.status_code, r.json()) == (404, unknown.json()) == (404, {"detail": "not found"})


@pytest.mark.parametrize(("value", "status"), [("1", 200), ("yes", 404), ("true", 404), ("", 404)])
def test_only_the_exact_flag_turns_the_routes_on(make, monkeypatch, value, status):
    build, conn = make
    _two_institutions(conn)
    monkeypatch.setenv("NZSTATS_PUBLIC_RESEARCH", value)
    assert build(enabled=None, reg=_reg()).get(ROUTES[0]).status_code == status


def test_the_app_without_the_research_router_never_serves_research(make, monkeypatch):
    # The snapshot exporter builds the app this way, so research cannot reach a public snapshot.
    build, conn = make
    _two_institutions(conn)
    monkeypatch.setenv("NZSTATS_PUBLIC_RESEARCH", "1")
    client = build(routers=[])
    assert all(client.get(route).status_code == 404 for route in ROUTES)


def test_enabled_with_nothing_eligible_is_an_empty_feed_not_an_error(make):
    build, conn = make
    v = seed_version(conn)
    store_summary(conn, v, publish=False)
    client = build()
    feed = client.get("/api/research/feed").json()
    assert (feed["items"], feed["total"], feed["institutions"]) == ([], 0, [])
    assert client.get("/api/research/forecasts").json()["groups"] == []
    assert client.get("/api/research/summaries/1").status_code == 404


def test_a_registry_that_cannot_be_read_fails_closed(make):
    build, conn = make
    _two_institutions(conn)

    def broken():
        raise RegistryError("bad file")

    client = build(reg=broken)
    assert client.get("/api/research/feed").json()["total"] == 0
    assert client.get("/api/research/summaries/1").status_code == 404


def test_feed_items_carry_only_public_fields(make):
    build, conn = make
    a, b = _two_institutions(conn)
    r = build(reg=_reg()).get("/api/research/feed")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    body = r.text
    for needle in PRIVATE:
        assert needle not in body, needle
    feed = r.json()
    assert [i["id"] for i in feed["items"]] == [b, a]  # newest publication first
    item = feed["items"][1]
    assert item["institution"] == {"key": "alpha", "name": "Example Research", "kind": "bank"}
    assert item["document"]["url"] == "https://research.example.org/a"
    assert item["document"]["published_on"] == "2026-08-13" and item["document"]["version_no"] == 1
    assert item["processing"]["human_reviewed_on"] == NOW.date().isoformat()
    assert item["processing"]["published_here_on"] == NOW.date().isoformat()
    assert (
        item["interpretation_label"].startswith("AI interpretation")
        and item["not_official_statistic"]
    )
    assert item["topics"] == ["economic_outlook"] and item["indicators"] == ["gdp", "cpi_inflation"]


def test_quotes_appear_only_at_the_excerpt_level(make):
    build, conn = make
    _two_institutions(conn)
    items = {
        i["institution"]["key"]: i
        for i in build(reg=_reg()).get("/api/research/feed").json()["items"]
    }
    assert items["alpha"]["outlook"]["evidence"][0]["quote"].startswith("The economy is expected")
    beta = items["beta"]["outlook"]
    assert beta["evidence"][0] == {"section_ordinal": 0, "page": 1, "quote": None}
    assert beta["text"].endswith(
        "<script>alert('x')</script>."
    )  # JSON data; the UI renders it as text


def test_link_only_shows_no_ai_text_and_search_cannot_reach_hidden_text(make):
    build, conn = make
    _two_institutions(conn)
    client = build(reg=_reg(alpha="link_only", beta="link_only"))
    items = client.get("/api/research/feed").json()["items"]
    for item in items:
        assert item["display"] == "link_only"
        assert (item["outlook"], item["drivers"], item["risks"], item["uncertainty"]) == (
            None,
            [],
            [],
            None,
        )
        assert item["indicators"] == [] and item["n_forecasts"] == 0
    assert client.get("/api/research/feed", params={"q": "growth recovers"}).json()["total"] == 0
    assert (
        client.get("/api/research/feed", params={"q": "synthetic outlook b"}).json()["total"] == 1
    )
    assert client.get("/api/research/forecasts").json()["groups"] == []


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"institution": "alpha"}, ["alpha"]),
        ({"institution": "nobody"}, []),
        ({"topic": "economic_outlook"}, ["beta", "alpha"]),
        ({"topic": "fiscal"}, []),
        ({"indicator": "gdp"}, ["beta", "alpha"]),
        ({"indicator": "ocr"}, []),
        ({"q": "GROWTH  RECOVERS"}, ["beta"]),
        ({"q": "  example research "}, ["beta", "alpha"]),
        ({"sort": "oldest"}, ["alpha", "beta"]),
        ({"sort": "institution"}, ["alpha", "beta"]),
        ({"limit": 1}, ["beta"]),
        ({"limit": 1, "offset": 1}, ["alpha"]),
        ({"offset": 5}, []),
    ],
)
def test_feed_filters_search_sort_and_pagination(make, params, expected):
    build, conn = make
    _two_institutions(conn)
    feed = build(reg=_reg()).get("/api/research/feed", params=params).json()
    assert [i["institution"]["key"] for i in feed["items"]] == expected
    if "limit" in params or "offset" in params:
        assert feed["total"] == 2 and feed["limit"] == params.get("limit", 20)


def test_facets_list_what_is_present(make):
    build, conn = make
    _two_institutions(conn)
    feed = build(reg=_reg()).get("/api/research/feed", params={"institution": "alpha"}).json()
    assert [(f["value"], f["count"]) for f in feed["institutions"]] == [("alpha", 1), ("beta", 1)]
    assert [f["value"] for f in feed["indicators"]] == ["gdp", "cpi_inflation"]
    assert feed["topics"][0] == {
        "value": "economic_outlook",
        "label": "Economic outlook",
        "count": 2,
    }


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 51}, {"offset": -1}, {"q": "x" * 101}, {"sort": "random"},
     {"institution": "a" * 300}, {"indicator": "<script>"}],
)  # fmt: skip
def test_feed_rejects_bad_parameters(make, params):
    build, conn = make
    assert build().get("/api/research/feed", params=params).status_code == 422


def test_detail_has_provenance_versions_and_forecasts(make):
    build, conn = make
    a, b = _two_institutions(conn)
    client = build(reg=_reg())
    r = client.get(f"/api/research/summaries/{a}")
    assert r.status_code == 200
    for needle in PRIVATE:
        assert needle not in r.text, needle
    detail = r.json()
    assert detail["item"]["id"] == a
    assert detail["provenance"] == {
        "provider": "fake", "model": "fake-1", "hosted": False, "prompt_version": "outlook-v2",
        "processing_version": "3b-1", "verifier_version": "verify-4", "created_at": "2026-10-26T14:00:00+13:00",
    }  # fmt: skip
    assert detail["versions"] == [
        {"version_no": 1, "fetched_at": "2026-10-26T14:00:00+13:00", "current": True}
    ]
    cpi = detail["forecasts"][1]
    assert (cpi["indicator"], cpi["value"], cpi["unit"], cpi["horizon"]) == (
        "cpi_inflation", 2.1, "percent", "year to June 2027")  # fmt: skip
    assert cpi["evidence"][0]["quote"] == "forecast to fall to 2.1% in the year to June 2027"
    beta = client.get(f"/api/research/summaries/{b}").json()
    assert beta["forecasts"][0]["evidence"][0]["quote"] is None


@pytest.mark.parametrize("sid", ["0", "-1", "99999", str(2**63), "abc"])
def test_detail_of_anything_not_public_is_not_found(make, sid):
    build, conn = make
    _two_institutions(conn)
    assert build(reg=_reg()).get(f"/api/research/summaries/{sid}").status_code in (404, 422)


def test_detail_of_an_unpublished_summary_is_not_found(make):
    build, conn = make
    sid = store_summary(conn, seed_version(conn), publish=False)
    assert build().get(f"/api/research/summaries/{sid}").status_code == 404


def test_forecasts_group_like_claims_and_explain_the_rest(make):
    build, conn = make
    _two_institutions(conn)
    client = build(reg=_reg())
    out = client.get("/api/research/forecasts").json()
    [group] = out["groups"]
    assert group["key"] == "cpi_inflation|percent|annual_change|year_to:2027-06|central"
    assert group["comparable"] and [r["forecast"]["institution"]["key"] for r in group["rows"]] == [
        "alpha",
        "beta",
    ]
    assert {e["forecast"]["indicator"] for e in out["excluded"]} == {"gdp"}
    assert "annual average" in out["excluded"][0]["reason"]
    assert [f["value"] for f in out["institutions"]] == ["alpha", "beta"]
    one = client.get("/api/research/forecasts", params={"institution": "alpha"}).json()
    assert (
        not one["groups"][0]["comparable"] and len(one["institutions"]) == 2
    )  # facets stay complete
    assert client.get("/api/research/forecasts", params={"indicator": "gdp"}).json()["groups"] == []
    assert (
        client.get("/api/research/forecasts", params={"horizon": "year_to:2027-03"}).json()[
            "groups"
        ]
        == []
    )
    both = client.get("/api/research/forecasts", params={"institution": "alpha,beta"}).json()
    assert both["groups"][0]["comparable"]


def test_forecast_responses_contain_no_private_fields(make):
    build, conn = make
    _two_institutions(conn)
    body = build(reg=_reg()).get("/api/research/forecasts").text
    for needle in PRIVATE:
        assert needle not in body, needle
    assert json.loads(body)["note"].startswith("Forecasts are compared only when")


def test_research_routes_are_read_only(make):
    build, conn = make
    _two_institutions(conn)
    client = build(reg=_reg())
    for route in ROUTES:
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)(route).status_code in (404, 405)


def test_the_database_is_opened_read_only_even_from_an_awkward_directory(tmp_path, monkeypatch):
    from nzstats.research.api import _read_only

    odd = tmp_path / "data ?#%"
    settings = load_settings({"NZSTATS_DATA_DIR": str(odd)})
    TestClient(create_app(settings))  # migrates
    c = _read_only(settings.db_path)
    assert c.execute("SELECT COUNT(*) FROM research_summary").fetchone()[0] == 0
    with pytest.raises(Exception, match="readonly"):
        c.execute("INSERT INTO research_llm_run(provider, model, hosted, prompt_version, processing_version,"
                  " started_at) VALUES ('p','m',0,'v','x','t')")  # fmt: skip


def test_a_third_party_forecast_is_never_shown_as_the_institutions_own(make):
    """Phase 4I: an IMF forecast quoted in a document is the IMF's, not the publishing institution's."""
    build, conn = make
    v = seed_version(conn, ("SYNTHETIC FIXTURE. We expect growth of 2.8% in 2027. The IMF expects"
                            " growth of 2.9% in 2027.",), key="alpha")  # fmt: skip

    def claim(value, quote, issuer, role):
        return {"indicator": "gdp", "indicator_label": "GDP growth", "horizon": "2027", "value": value,
                "unit": "percent", "direction": "unclear", "issuer": issuer, "issuer_role": role,
                "evidence": [{"version_id": v, "section_ordinal": 0, "page": 1, "quote": quote}]}  # fmt: skip

    own = claim(2.8, "We expect growth of 2.8% in 2027", "Example Research", "author")
    imf = claim(2.9, "The IMF expects growth of 2.9% in 2027", "IMF", "third_party")
    out = draft(v, forecasts=[own, imf], indicators=["gdp"],
                outlook={"text": "Growth is expected.", "evidence": own["evidence"]})  # fmt: skip
    sid = store_summary(conn, v, output=out)
    client = build(reg=registry(displayable("alpha")))
    detail = client.get(f"/api/research/summaries/{sid}").json()
    assert [f["value"] for f in detail["forecasts"]] == [2.8]
    assert detail["item"]["n_forecasts"] == 1
    assert "2.9" not in client.get("/api/research/forecasts").text

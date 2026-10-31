"""The private research preview routes (Phase 4I): off by default, local dashboard only, an allowlist (SYNTHETIC FIXTURE)."""

import pytest

from nzstats.research.private_api import CLIENT_HEADER, private_research_router

from .llm_support import SECTIONS, draft, seed_version
from .public_support import store_summary
from .test_private import previewable

LOCAL = {"host": "127.0.0.1:8000", CLIENT_HEADER: "dashboard"}
FEED = "/api/private/research/items"
PRIVATE_TEXT = ("RAW MODEL OUTPUT", "PRIVATE REVIEW NOTE", "Private Reviewer Name", "Private Approver",
                "raw_output", "parameters", "temperature", "input_sha256", "cost_usd", SECTIONS[0])  # fmt: skip


@pytest.fixture()
def preview(make):
    build, conn = make
    v = seed_version(conn, ("SYNTHETIC FIXTURE. We expect growth of 2.8% in 2027. The IMF expects growth"
                            " of 2.9% in 2027.",))  # fmt: skip

    def claim(value, quote, issuer, role):
        return {"indicator": "gdp", "indicator_label": "GDP growth", "horizon": "2027", "value": value,
                "unit": "percent", "direction": "unclear", "issuer": issuer, "issuer_role": role,
                "evidence": [{"version_id": v, "section_ordinal": 0, "page": 1, "quote": quote}]}  # fmt: skip

    own = claim(2.8, "We expect growth of 2.8% in 2027", "Example Research", "author")
    imf = claim(2.9, "The IMF expects growth of 2.9% in 2027", "IMF", "third_party")
    out = draft(v, forecasts=[own, imf], indicators=["gdp"],
                outlook={"text": "Growth is expected.", "evidence": own["evidence"]})  # fmt: skip
    sid = store_summary(conn, v, output=out, publish=False)
    reg = {"example": previewable()}

    def client(*, enabled=True, registry=None):
        loader = registry if registry is not None else (lambda: reg)
        return build(routers=[private_research_router(enabled=enabled, registry=loader)])

    return client, sid


def test_the_routes_are_off_unless_enabled_and_then_indistinguishable_from_an_unknown_path(preview):
    client, sid = preview
    off = client(enabled=False)
    unknown = off.get("/api/no-such-thing", headers=LOCAL)
    for route in (FEED, f"{FEED}/{sid}"):
        r = off.get(route, headers=LOCAL)
        assert (r.status_code, r.json()) == (404, unknown.json())


@pytest.mark.parametrize(
    "headers",
    [
        {"host": "127.0.0.1:8000"},  # no client header
        {"host": "evil.example:8000", CLIENT_HEADER: "dashboard"},  # DNS rebinding
        {"host": "192.168.1.20:8000", CLIENT_HEADER: "dashboard"},
        {**LOCAL, "origin": "http://evil.example"},
        {**LOCAL, "sec-fetch-site": "cross-site"},
        {**LOCAL, CLIENT_HEADER: "other"},
    ],
)
def test_only_the_local_dashboard_may_read_the_preview(preview, headers):
    client, sid = preview
    for route in (FEED, f"{FEED}/{sid}"):
        assert client().get(route, headers=headers).status_code == 403


def test_the_feed_labels_every_block_and_never_mixes_in_official_statistics(preview):
    client, sid = preview
    r = client().get(FEED, headers={**LOCAL, "origin": "http://127.0.0.1:8000"})
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"]
    for needle in PRIVATE_TEXT:
        assert needle not in r.text, needle
    (item,) = r.json()["items"]
    assert item["id"] == sid and item["official_statistic"] is False
    assert "Not an official statistic" in item["label"]
    assert item["document"]["published_on"] == "2026-08-13" and item["document"]["url"].startswith(
        "https://"
    )
    assert item["review"]["human_reviewed_on"] and item["review"]["verifier_version"] == "verify-3"
    kinds = [(b["kind"], b.get("issuer"), b.get("value")) for b in item["blocks"]]
    assert ("institutional_view", None, None) in kinds
    assert ("forecast", "Example Research", 2.8) in kinds
    assert (
        "third_party_forecast",
        "IMF",
        2.9,
    ) in kinds  # labelled as the IMF's, never the institution's
    for block in item["blocks"]:
        assert (
            block["badge"] and block["evidence"][0]["quote"] and block["evidence"][0]["page"] == 1
        )


def test_the_detail_matches_the_feed_and_anything_not_previewable_is_not_found(preview):
    client, sid = preview
    c = client()
    detail = c.get(f"{FEED}/{sid}", headers=LOCAL)
    assert (
        detail.status_code == 200 and detail.json() == c.get(FEED, headers=LOCAL).json()["items"][0]
    )
    for missing in (sid + 1, 0, 2**63):
        assert c.get(f"{FEED}/{missing}", headers=LOCAL).status_code in (404, 422)


def test_an_unreadable_registry_shows_nothing(preview):
    client, _ = preview

    def broken():
        raise OSError("registry file missing")

    r = client(registry=broken).get(FEED, headers=LOCAL)
    assert r.status_code == 200 and r.json()["items"] == []


def test_the_routes_never_write_or_accept_other_methods(preview):
    client, sid = preview
    for method in ("post", "put", "delete"):
        assert getattr(client(), method)(FEED, headers=LOCAL).status_code == 405

"""The internal draft routes: off by default, local dashboard only, an allowlisted response (SYNTHETIC FIXTURE)."""

import json

import pytest

from nzstats.research.drafts_api import draft_bind_refusal, internal_drafts_router
from nzstats.research.private_api import CLIENT_HEADER

from .llm_support import SECTIONS, draft, seed_version
from .public_support import store_summary
from .support import institution

LOCAL = {"host": "127.0.0.1:8000", CLIENT_HEADER: "dashboard"}
FEED = "/api/internal/drafts"
PRIVATE_TEXT = ("RAW MODEL OUTPUT", "raw_output", "parameters", "temperature", "input_sha256", "cost_usd",
                "output_sha256", "Test Owner", "OWNER NOTE", SECTIONS[0])  # fmt: skip


@pytest.fixture()
def drafts(make, tmp_path):
    build, conn = make
    v = seed_version(conn)
    out = draft(v)
    out["forecasts"][0]["value"] = 9.9  # not in the evidence
    sid = store_summary(conn, v, output=out, review=None, publish=False)
    digest = conn.execute(
        "SELECT output_sha256 FROM research_summary WHERE id = ?", (sid,)
    ).fetchone()[0]
    (tmp_path / "data" / "internal-drafts.json").write_text(
        json.dumps({"drafts": [{"summary_id": sid, "output_sha256": digest, "approved_by": "Test Owner",
                                "approved_on": "2026-11-02", "note": "OWNER NOTE"}]})
    )  # fmt: skip
    reg = {"example": institution()}

    def client(*, enabled=True, registry=None):
        loader = registry if registry is not None else (lambda: reg)
        return build(routers=[internal_drafts_router(enabled=enabled, registry=loader)])

    return client, sid, tmp_path / "data" / "internal-drafts.json"


def test_the_routes_are_off_unless_enabled_and_then_indistinguishable_from_an_unknown_path(drafts):
    client, sid, _ = drafts
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
def test_only_the_local_dashboard_may_read_a_draft(drafts, headers):
    client, sid, _ = drafts
    for route in (FEED, f"{FEED}/{sid}"):
        assert client().get(route, headers=headers).status_code == 403


def test_a_draft_says_what_it_is_and_marks_every_claim(drafts):
    client, sid, _ = drafts
    r = client().get(FEED, headers={**LOCAL, "origin": "http://127.0.0.1:8000"})
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"]
    (item,) = r.json()["items"]
    assert item["id"] == sid and item["official_statistic"] is False
    assert item["checks_passed"] is False and item["human_reviewed"] is False
    assert item["approved_for_publication"] is False
    assert "failed" in item["label"] and "Not an official statistic" in item["label"]
    assert item["counts"] == {"clean": 2, "warning": 0, "failed": 1}
    assert item["provenance"]["verifier_version"] == "verify-3"
    by_path = {c["path"]: c for c in item["claims"]}
    assert set(by_path) == {"outlook", "forecasts[0]", "forecasts[1]"}
    failed = by_path["forecasts[0]"]
    assert failed["status"] == "failed" and failed["kind"] == "forecast"
    assert failed["problems"][0]["code"] and failed["problems"][0]["severity"] == "error"
    assert failed["evidence"][0]["quote"]
    assert by_path["outlook"]["status"] == "clean" and by_path["outlook"]["problems"] == []


def test_the_response_is_an_allowlist(drafts):
    client, _, _ = drafts
    r = client().get(FEED, headers=LOCAL)
    for needle in PRIVATE_TEXT:
        assert needle not in r.text, needle


def test_the_detail_matches_the_feed_and_anything_not_listed_is_not_found(drafts):
    client, sid, _ = drafts
    c = client()
    detail = c.get(f"{FEED}/{sid}", headers=LOCAL)
    assert (
        detail.status_code == 200 and detail.json() == c.get(FEED, headers=LOCAL).json()["items"][0]
    )
    for missing in (sid + 1, 0, 2**63):
        assert c.get(f"{FEED}/{missing}", headers=LOCAL).status_code in (404, 422)


def test_an_unreadable_registry_shows_nothing(drafts):
    client, _, _ = drafts

    def broken():
        raise OSError("registry file missing")

    r = client(registry=broken).get(FEED, headers=LOCAL)
    assert r.status_code == 200 and r.json()["items"] == []


def test_a_malformed_list_shows_nothing_and_a_missing_list_shows_nothing(drafts):
    client, _, path = drafts
    path.write_text("not json")
    r = client().get(FEED, headers=LOCAL)
    assert r.status_code == 200 and r.json()["items"] == []
    path.unlink()
    r = client().get(FEED, headers=LOCAL)
    assert r.status_code == 200 and r.json()["items"] == []


def test_the_feed_lists_stored_reports_with_only_their_public_details(drafts, make):
    client, _, path = drafts
    path.unlink()  # a report with no AI summary is still listed
    _, conn = make
    seed_version(conn, doc="newer", published_on="2026-11-02")
    r = client().get(FEED, headers=LOCAL)
    assert r.status_code == 200 and r.json()["items"] == []
    newest, earlier = r.json()["reports"]
    assert set(newest) == {"institution", "institution_name", "title", "url", "series", "published_on",
                           "newest", "draft_id"}  # fmt: skip
    assert (newest["title"], newest["published_on"], newest["newest"], newest["draft_id"]) == (
        "Synthetic outlook newer", "2026-11-02", True, None)  # fmt: skip
    assert (earlier["published_on"], earlier["newest"]) == ("2026-08-13", False)


def test_a_report_links_to_its_draft_and_a_draft_says_when_a_newer_report_exists(drafts, make):
    client, sid, _ = drafts
    _, conn = make
    c = client()
    assert c.get(f"{FEED}/{sid}", headers=LOCAL).json()["newer_report"] is None
    seed_version(conn, doc="newer", published_on="2026-11-02")
    body = c.get(FEED, headers=LOCAL).json()
    assert body["reports"][1]["draft_id"] == sid and body["reports"][0]["draft_id"] is None
    newer = {"title": "Synthetic outlook newer", "published_on": "2026-11-02"}
    assert body["items"][0]["newer_report"] == newer
    assert c.get(f"{FEED}/{sid}", headers=LOCAL).json()["newer_report"] == newer


def test_a_draft_of_a_report_published_on_the_same_day_is_not_told_a_newer_one_exists(drafts, make):
    client, sid, _ = drafts
    _, conn = make
    seed_version(conn, doc="same-day", published_on="2026-08-13")
    assert client().get(f"{FEED}/{sid}", headers=LOCAL).json()["newer_report"] is None


def test_an_unreadable_registry_lists_no_reports(drafts):
    client, _, _ = drafts

    def broken():
        raise OSError("registry file missing")

    assert client(registry=broken).get(FEED, headers=LOCAL).json()["reports"] == []


def test_a_malformed_list_lists_no_reports(drafts):
    client, _, path = drafts
    path.write_text("not json")
    assert client().get(FEED, headers=LOCAL).json()["reports"] == []


def test_the_routes_never_accept_other_methods(drafts):
    client, _, _ = drafts
    for method in ("post", "put", "delete"):
        assert getattr(client(), method)(FEED, headers=LOCAL).status_code == 405


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_loopback_binds_are_allowed(host):
    assert draft_bind_refusal(host) is None


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "::", "dashboard.example"])
def test_any_other_bind_is_refused(host):
    assert "refusing" in draft_bind_refusal(host)

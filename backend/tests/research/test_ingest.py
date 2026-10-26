"""End-to-end research ingest against a fake site. Every body is SYNTHETIC FIXTURE text."""

import json
from datetime import timedelta

import httpx
import pytest

from nzstats.domain import RequestRefused
from nzstats.research import store
from nzstats.research.ingest import run_institution
from nzstats.sources.artifacts import ArtifactStore

from .conftest import NOW
from .pdf_support import text_pdf
from .support import BASE, ROBOTS, FakeClock, Site, institution, research_fetcher

LISTING = f"{BASE}/research/"
DOC_A = f"{BASE}/research/outlook-a"
DOC_B = f"{BASE}/research/outlook-b"
PDF = f"{BASE}/research/ANZ-QEO-20260813.pdf"
PARA = "The example economy is assumed to grow slowly in this synthetic fixture text. "


def report(title: str, words: str = PARA * 6, published: str | None = "2026-08-13") -> str:
    meta = f'<meta property="article:published_time" content="{published}">' if published else ""
    return (
        f"<html><head><title>{title}</title>{meta}</head><body><nav>menu</nav><main>"
        f"<h1>{title}</h1><p>{words}</p><h2>Risks</h2><p>{PARA * 2}</p></main></body></html>"
    )


def listing(*urls: str) -> str:
    links = "".join(f'<a href="{u}">Report {i}</a>' for i, u in enumerate(urls))
    return f"<html><body><main>{links}</main></body></html>"


def site(**pages) -> Site:
    base = {ROBOTS: "User-agent: *\nDisallow: /members/\n", LISTING: listing(DOC_A)}
    base.update(pages)
    return Site(base)


@pytest.fixture()
def artifacts(tmp_path):
    return ArtifactStore(tmp_path / "raw")


def run(conn, inst, web, artifacts=None, *, at=NOW, clock=None, **kw):
    fetcher = research_fetcher(inst, web, clock=clock, now=lambda: at)
    return run_institution(conn, inst, fetcher, artifacts=artifacts, now_fn=lambda: at, **kw)


def outcomes(result):
    return [i.outcome for i in result.items]


def pub_row(conn, url=DOC_A):
    return conn.execute(
        "SELECT * FROM research_publication WHERE canonical_url=?", (url,)
    ).fetchone()


def current_text(conn, url=DOC_A):
    pub = pub_row(conn, url)
    return " ".join(r["text"] for r in conn.execute(
        "SELECT text FROM research_section WHERE version_id=? ORDER BY ordinal",
        (pub["current_version_id"],)))  # fmt: skip


# --- access gates ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"review_status": "restricted"}, "restricted"),
        ({"review_status": "needs_review"}, "needs review"),
    ],
)
def test_sources_without_approval_make_zero_requests(conn, overrides, reason):
    web = site()
    inst = institution(**overrides, approved_by=None, approved_on=None, approval_note=None)
    result = run(conn, inst, web)
    assert result.outcome == "refused" and reason in (result.refusal or "")
    assert web.requests == []
    assert conn.execute("SELECT COUNT(*) FROM research_publication").fetchone()[0] == 0


def test_restricted_source_refuses_even_a_dry_run(conn):
    web = site()
    inst = institution(review_status="restricted", approved_by=None, approved_on=None,
                       approval_note=None)  # fmt: skip
    assert run(conn, inst, web, dry_run=True).outcome == "refused"
    assert web.requests == []


def test_needs_review_allows_a_discovery_only_dry_run_that_writes_nothing(conn):
    web = site(**{LISTING: listing(DOC_A, DOC_B)})
    inst = institution(review_status="needs_review", approved_by=None, approved_on=None,
                       approval_note=None)  # fmt: skip
    result = run(conn, inst, web, dry_run=True)
    assert result.outcome == "dry_run"
    assert [c.url for c in result.candidates] == [DOC_A, DOC_B]
    assert web.requests == [ROBOTS, LISTING]  # no document requested
    assert conn.execute("SELECT COUNT(*) FROM research_run").fetchone()[0] == 0


def test_metadata_only_never_downloads_the_document(conn):
    pdf_listing = listing(PDF)
    web = site(**{LISTING: pdf_listing})
    inst = institution(
        content_policy="metadata_only",
        url_date_regex=r"ANZ-[A-Z]+-(\d{8})\.pdf$",
        url_date_format="%Y%m%d",
    )
    result = run(conn, inst, web)
    assert outcomes(result) == ["link_only"]
    assert PDF not in web.requests
    row = pub_row(conn, PDF)
    assert row["content_status"] == "link_only" and row["current_version_id"] is None
    assert (row["published_on"], row["published_precision"]) == ("2026-08-13", "day")
    assert row["title"] == "Report 0"
    assert outcomes(run(conn, inst, site(**{LISTING: pdf_listing}))) == ["unchanged"]


# --- happy paths and revisions --------------------------------------------------------------


def test_full_text_html_is_stored_with_provenance(conn, artifacts):
    result = run(conn, institution(), site(**{DOC_A: report("Outlook A")}), artifacts)
    assert outcomes(result) == ["new"] and result.outcome == "ok"
    row = pub_row(conn)
    assert row["doc_key"] == "example:research.example.org/research/outlook-a"
    assert row["title"] == "Outlook A" and row["content_status"] == "extracted"
    assert (row["published_on"], row["published_at"], row["published_precision"]) == (
        "2026-08-13", None, "day")  # fmt: skip
    assert row["reference_period"] is None  # never derived from the publication date
    version = store.current_version(conn, row["id"])
    assert version["format"] == "html" and version["extractor_version"] == "html-1"
    assert version["fetched_at"] == "2026-10-25T01:00:00Z"
    assert json.loads(version["licence_snapshot"])["approved_by"] == "Test Reviewer"
    raw = conn.execute(
        "SELECT * FROM raw_artifact WHERE id=?", (version["raw_artifact_id"],)
    ).fetchone()
    assert raw["url"] == DOC_A and len(raw["sha256"]) == 64
    headings = [r[0] for r in conn.execute(
        "SELECT heading FROM research_section WHERE version_id=? ORDER BY ordinal", (version["id"],))]  # fmt: skip
    assert headings == ["Outlook A", "Risks"]
    assert "menu" not in current_text(conn)
    health = conn.execute("SELECT * FROM research_source_health").fetchone()
    assert health["state"] == "ok" and health["consecutive_failures"] == 0


def test_full_text_pdf_with_date_from_the_file_name(conn):
    body = text_pdf([[f"Example outlook {i} (SYNTHETIC FIXTURE)", PARA * 2] for i in range(3)])
    web = site(**{LISTING: listing(PDF), PDF: (200, {"content-type": "application/pdf"}, body)})
    inst = institution(url_date_regex=r"ANZ-[A-Z]+-(\d{8})\.pdf$", url_date_format="%Y%m%d")
    assert outcomes(run(conn, inst, web)) == ["new"]
    row = pub_row(conn, PDF)
    assert row["published_on"] == "2026-08-13"
    version = store.current_version(conn, row["id"])
    assert (version["format"], version["page_count"]) == ("pdf", 3)
    pages = [tuple(r) for r in conn.execute(
        "SELECT page_start, page_end FROM research_section WHERE version_id=?", (version["id"],))]  # fmt: skip
    assert pages == [(1, 1), (2, 2), (3, 3)]


def test_unchanged_rerun_adds_no_version(conn):
    inst = institution()
    run(conn, inst, site(**{DOC_A: report("Outlook A")}))
    later = NOW + timedelta(days=1)
    assert outcomes(run(conn, inst, site(**{DOC_A: report("Outlook A")}), at=later)) == [
        "unchanged"
    ]
    assert conn.execute("SELECT COUNT(*) FROM research_document_version").fetchone()[0] == 1
    assert pub_row(conn)["last_seen_at"] == "2026-10-26T01:00:00Z"


def test_whitespace_only_change_is_unchanged(conn):
    inst = institution()
    run(conn, inst, site(**{DOC_A: report("Outlook A")}))
    respaced = report("Outlook A").replace("<p>", "<p>\n\n   ")
    assert outcomes(run(conn, inst, site(**{DOC_A: respaced}))) == ["unchanged"]


def test_changed_text_adds_version_two_and_a_revert_reactivates_version_one(conn):
    inst = institution()
    a, b = report("Outlook A"), report("Outlook A", PARA * 5 + "Revised paragraph. ")
    run(conn, inst, site(**{DOC_A: a}))
    v1 = pub_row(conn)["current_version_id"]
    assert outcomes(run(conn, inst, site(**{DOC_A: b}), at=NOW + timedelta(hours=1))) == ["updated"]
    v2 = pub_row(conn)["current_version_id"]
    assert v2 != v1
    superseded = conn.execute(
        "SELECT superseded_at FROM research_document_version WHERE id=?", (v1,)
    )
    assert superseded.fetchone()[0] == "2026-10-25T02:00:00Z"
    assert outcomes(run(conn, inst, site(**{DOC_A: a}), at=NOW + timedelta(hours=2))) == [
        "reactivated"
    ]
    assert pub_row(conn)["current_version_id"] == v1
    assert conn.execute("SELECT COUNT(*) FROM research_document_version").fetchone()[0] == 2


def test_same_text_under_a_second_url_is_a_duplicate(conn):
    web = site(
        **{LISTING: listing(DOC_A, DOC_B), DOC_A: report("Outlook"), DOC_B: report("Outlook")}
    )
    result = run(conn, institution(), web)
    assert outcomes(result) == ["new", "duplicate"]
    dup = pub_row(conn, DOC_B)
    assert dup["duplicate_of_id"] == pub_row(conn, DOC_A)["id"]
    assert dup["current_version_id"] is None and dup["content_status"] == "link_only"
    assert conn.execute("SELECT COUNT(*) FROM research_document_version").fetchone()[0] == 1


# --- failures keep the last good version --------------------------------------------------------


def _store_good(conn, inst):
    run(conn, inst, site(**{DOC_A: report("Outlook A")}))
    return pub_row(conn)["current_version_id"]


@pytest.mark.parametrize(
    "page,error_class",
    [
        ((403, {}, b"forbidden"), "blocked"),
        (
            report("Sign in", "Please log in to continue reading this report. " + PARA * 4),
            "validation_failed",
        ),
        (report("Wait", "Checking your browser before accessing the site. " + PARA * 4), "blocked"),
        (report("Teaser", "Short teaser."), "validation_failed"),
        (report("Outlook A", PARA), "validation_failed"),  # truncated: under half the stored text
        ((200, {"content-type": "application/pdf"}, b"<html>not a pdf</html>"), "layout_changed"),
        ((200, {"content-type": "text/plain"}, b"plain"), "unexpected"),
    ],
)
def test_a_bad_fetch_records_a_failure_and_keeps_the_previous_version(conn, page, error_class):
    inst = institution()
    good = _store_good(conn, inst)
    result = run(conn, inst, site(**{DOC_A: page}), at=NOW + timedelta(days=1))
    assert outcomes(result) == ["failed"] and result.items[0].error_class == error_class
    assert pub_row(conn)["current_version_id"] == good
    assert conn.execute("SELECT COUNT(*) FROM research_document_version").fetchone()[0] == 1
    health = conn.execute("SELECT * FROM research_source_health").fetchone()
    assert health["state"] in ("degraded", "failing", "blocked")
    assert health["consecutive_failures"] == 1
    assert health["last_success_at"] == "2026-10-25T01:00:00Z"


def test_404_on_a_known_document_keeps_its_content(conn):
    inst = institution()
    good = _store_good(conn, inst)
    web = site()  # DOC_A is listed but no longer served: 404
    result = run(conn, inst, web)
    assert outcomes(result) == ["failed"] and result.items[0].error_class == "not_found"
    assert pub_row(conn)["current_version_id"] == good


def test_transient_errors_are_retried_and_retry_after_is_honoured(conn):
    clock = FakeClock()
    answers = iter([httpx.Response(503, headers={"retry-after": "7"}), httpx.Response(
        200, headers={"content-type": "text/html"}, content=report("Outlook A").encode())])  # fmt: skip
    web = site(**{DOC_A: lambda request: next(answers)})
    assert outcomes(run(conn, institution(), web, clock=clock)) == ["new"]
    assert web.requests.count(DOC_A) == 2 and any(s >= 7 for s in clock.sleeps)


def test_network_failure_is_recorded_after_retries(conn):
    def down(request):
        raise httpx.ConnectError("boom")

    web = site(**{DOC_A: down})
    result = run(conn, institution(), web)
    assert outcomes(result) == ["failed"] and result.items[0].error_class == "network"
    assert web.requests.count(DOC_A) == 3  # 1 + 2 retries


def test_a_block_stops_the_run(conn):
    web = site(**{LISTING: listing(DOC_A, DOC_B), DOC_A: (403, {}, b"no"), DOC_B: report("B")})
    result = run(conn, institution(), web)
    assert outcomes(result) == ["failed"] and result.outcome == "blocked"
    assert DOC_B not in web.requests


def test_one_bad_document_does_not_stop_the_rest(conn):
    web = site(**{LISTING: listing(DOC_A, DOC_B), DOC_A: report("A", "tiny"), DOC_B: report("B")})
    result = run(conn, institution(), web)
    assert outcomes(result) == ["failed", "new"] and result.outcome == "partial"


def test_deeply_nested_json_ld_does_not_abort_the_run(conn):
    nested = "[" * 200_000 + "]" * 200_000
    page = report("A").replace(
        "</head>", f'<script type="application/ld+json">{nested}</script></head>'
    )
    web = site(**{LISTING: listing(DOC_A, DOC_B), DOC_A: page, DOC_B: report("B")})
    result = run(conn, institution(), web)
    assert outcomes(result) == ["new", "new"]


def test_an_unexpected_extractor_error_fails_that_document_only(conn, monkeypatch):
    from nzstats.research import ingest

    real = ingest.extract_html

    def flaky(body, content_type, limits):
        if b"Report A" in body:
            raise RuntimeError("secret upstream detail")
        return real(body, content_type, limits)

    monkeypatch.setattr(ingest, "extract_html", flaky)
    web = site(
        **{
            LISTING: listing(DOC_A, DOC_B),
            DOC_A: report("Report A"),
            DOC_B: report("B"),
        }
    )
    result = run(conn, institution(), web)
    assert outcomes(result) == ["failed", "new"]
    assert "secret upstream detail" not in repr(result.items[0])


def test_robots_and_unsafe_candidates_are_skipped_not_fetched(conn):
    members = f"{BASE}/members/report"
    web = site(**{LISTING: listing(members, DOC_A), DOC_A: report("A")})
    inst = institution(
        discovery=[{"mechanism": "html_links", "url": LISTING, "link_pattern": r"^https://.+"}]
    )
    result = run(conn, inst, web)
    assert outcomes(result) == ["skipped_robots", "new"]
    assert members not in web.requests


def test_max_documents_per_run_and_limit_are_honoured(conn):
    urls = [f"{BASE}/research/r{i}" for i in range(8)]
    pages = {u: report(f"R{i}", PARA * 6 + f"Unique {i}. ") for i, u in enumerate(urls)}
    web = site(**{LISTING: listing(*urls)}, **pages)
    assert len(run(conn, institution(max_documents_per_run=3), web).items) == 3
    assert len(run(conn, institution(), web, limit=2).items) == 2


def test_disagreeing_dates_warn_and_the_page_wins(conn):
    inst = institution(url_date_regex=r"-(\d{8})$", url_date_format="%Y%m%d")
    url = f"{BASE}/research/outlook-20260801"
    web = site(**{LISTING: listing(url), url: report("Outlook", published="2026-08-13")})
    result = run(conn, inst, web)
    assert "date_sources_disagree" in result.items[0].warnings
    assert pub_row(conn, url)["published_on"] == "2026-08-13"


def test_unparseable_page_date_falls_back_and_warns(conn):
    inst = institution(url_date_regex=r"-(\d{8})$", url_date_format="%Y%m%d")
    url = f"{BASE}/research/outlook-20260801"
    web = site(**{LISTING: listing(url), url: report("Outlook", published="sometime soon")})
    result = run(conn, inst, web)
    assert "unparsed_page_date" in result.items[0].warnings
    assert pub_row(conn, url)["published_on"] == "2026-08-01"


def test_stored_details_never_contain_upstream_text(conn):
    hostile = (200, {"content-type": "text/x-IGNORE-PREVIOUS-INSTRUCTIONS"}, b"x")
    web = site(**{DOC_A: hostile})
    run(conn, institution(), web)
    details = [r[0] or "" for r in conn.execute("SELECT detail FROM research_run_item")]
    details += [r[0] or "" for r in conn.execute("SELECT detail FROM research_run")]
    details += [r[0] or "" for r in conn.execute("SELECT detail FROM research_source_health")]
    assert details and not any("IGNORE" in d or "http" in d for d in details)


def test_a_failure_mid_write_leaves_no_partial_version(conn, monkeypatch):
    inst = institution()
    good = _store_good(conn, inst)
    real = store.add_version

    def explode(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("disk full")

    monkeypatch.setattr("nzstats.research.ingest.store.add_version", explode)
    changed = report("Outlook A", PARA * 5 + "Revised. ")
    result = run(conn, inst, site(**{DOC_A: changed}), at=NOW + timedelta(days=1))
    assert outcomes(result) == ["failed"] and result.items[0].detail == "unexpected (RuntimeError)"
    assert pub_row(conn)["current_version_id"] == good
    assert conn.execute("SELECT COUNT(*) FROM research_document_version").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM research_section").fetchone()[0] == 2


def test_run_and_items_are_recorded(conn):
    run(conn, institution(), site(**{DOC_A: report("Outlook A")}))
    row = conn.execute("SELECT * FROM research_run").fetchone()
    assert row["outcome"] == "ok" and row["dry_run"] == 0
    assert json.loads(row["counts"]) == {"new": 1}
    item = conn.execute("SELECT * FROM research_run_item").fetchone()
    assert (item["url"], item["outcome"]) == (DOC_A, "new") and item["version_id"] is not None


def test_discovery_failure_marks_the_source_failing(conn):
    web = site(**{LISTING: (500, {}, b"down")})
    result = run(conn, institution(), web)
    assert result.outcome == "failed" and result.items == []
    assert conn.execute("SELECT state FROM research_source_health").fetchone()[0] == "failing"


@pytest.mark.parametrize("limit", [0, -1])
def test_a_non_positive_limit_never_lifts_the_per_run_cap(conn, limit):
    urls = [f"{BASE}/research/r{i}" for i in range(8)]
    pages = {u: report(f"R{i}") for i, u in enumerate(urls)}
    web = site(**{LISTING: listing(*urls), **pages})
    result = run(conn, institution(max_documents_per_run=3), web, limit=limit)
    assert len(result.items) <= 3


def test_a_redirect_to_a_different_page_never_replaces_the_document(conn):
    inst = institution()
    good = _store_good(conn, inst)
    web = site(**{DOC_A: (301, {"location": DOC_B}, b""), DOC_B: report("Section index")})
    result = run(conn, inst, web, at=NOW + timedelta(days=1))
    assert outcomes(result) == ["failed"] and result.items[0].error_class == "unexpected"
    assert pub_row(conn)["current_version_id"] == good
    assert conn.execute("SELECT COUNT(*) FROM research_document_version").fetchone()[0] == 1


def test_a_cosmetic_redirect_to_the_same_document_is_followed(conn):
    inst = institution()
    web = site(**{DOC_A: (301, {"location": DOC_A + "/"}, b""), DOC_A + "/": report("A")})
    assert outcomes(run(conn, inst, web)) == ["new"]


@pytest.mark.parametrize(
    "target", [DOC_A.replace("/research/", "/Research/"), DOC_A + "/", DOC_A.replace("-", "%2D")]
)
def test_cosmetic_path_differences_in_a_redirect_are_the_same_document(conn, target):
    web = site(**{DOC_A: (301, {"location": target}, b""), target: report("A")})
    assert outcomes(run(conn, institution(), web)) == ["new"]


CHALLENGE = report("Wait", "Please verify you are human before reading this report. " + PARA * 4)


def _pacer(tmp_path, inst, clock):
    from nzstats.research.fetch import research_pacer

    return research_pacer(tmp_path, inst, sleep=clock.sleep, wall=clock)


def _paced_run(conn, inst, web, tmp_path, clock):
    fetcher = research_fetcher(inst, web, clock=clock, pacer=_pacer(tmp_path, inst, clock))
    result = run_institution(conn, inst, fetcher, now_fn=lambda: NOW)
    return result, fetcher


def test_a_challenge_found_by_validation_starts_the_institution_cooldown(conn, tmp_path):
    inst, clock = institution(), FakeClock()
    web = site(**{LISTING: listing(DOC_A, DOC_B), DOC_A: CHALLENGE, DOC_B: report("B")})
    result, fetcher = _paced_run(conn, inst, web, tmp_path, clock)
    assert result.outcome == "blocked" and DOC_B not in web.requests
    # The same fetcher now refuses everything...
    before = list(web.requests)
    with pytest.raises(RequestRefused):
        fetcher.get(DOC_B)
    assert web.requests == before
    # ...and so does another process (a new fetcher on the same pacing file) a minute later.
    clock.t += 60
    later = site(**{DOC_A: report("A")})
    other = research_fetcher(inst, later, clock=clock, pacer=_pacer(tmp_path, inst, clock))
    with pytest.raises(RequestRefused):
        other.get(DOC_A)
    assert later.requests == []


def test_the_challenge_cooldown_ends_after_thirty_minutes(conn, tmp_path):
    inst, clock = institution(), FakeClock()
    _paced_run(conn, inst, site(**{DOC_A: CHALLENGE}), tmp_path, clock)
    clock.t += 31 * 60
    later = site(**{DOC_A: report("A")})
    other = research_fetcher(inst, later, clock=clock, pacer=_pacer(tmp_path, inst, clock))
    assert other.get(DOC_A).body.startswith(b"<html>")
    assert DOC_A in later.requests


def test_a_challenge_without_a_shared_pacer_still_blocks_this_fetcher(conn):
    inst = institution()
    web = site(**{LISTING: listing(DOC_A, DOC_B), DOC_A: CHALLENGE, DOC_B: report("B")})
    fetcher = research_fetcher(inst, web)
    result = run_institution(conn, inst, fetcher, now_fn=lambda: NOW)
    assert result.outcome == "blocked"
    with pytest.raises(RequestRefused):
        fetcher.get(DOC_B)


def test_a_challenge_is_still_a_block_if_the_cooldown_cannot_be_saved(conn, tmp_path, monkeypatch):
    import os

    inst, clock = institution(), FakeClock()
    web = site(**{LISTING: listing(DOC_A, DOC_B), DOC_A: CHALLENGE, DOC_B: report("B")})
    fetcher = research_fetcher(inst, web, clock=clock, pacer=_pacer(tmp_path, inst, clock))
    real, calls = os.pwrite, []

    def fail_after_the_document_request(fd, data, offset):
        calls.append(1)
        # Writes 1-2 and 3-4 are the robots and listing requests, 5-6 the document's own turn;
        # everything after that is the block being published.
        if len(calls) > 6:
            raise OSError("private disk error")
        return real(fd, data, offset)

    monkeypatch.setattr(os, "pwrite", fail_after_the_document_request)
    result = run_institution(conn, inst, fetcher, now_fn=lambda: NOW)
    assert len(calls) > 6, "the cooldown save was never attempted"
    assert result.outcome == "blocked" and DOC_B not in web.requests
    assert "private" not in " ".join(str(i.detail) for i in result.items)
    with pytest.raises(RequestRefused):  # still refused in memory although the save failed
        fetcher.get(DOC_B)


def _many(n, *, changed=()):
    urls = [f"{BASE}/research/r{i}" for i in range(n)]
    pages = {
        u: report(f"R{i}", PARA * 6 + f"Unique {i}. " + ("Revised. " * 30 if i in changed else ""))
        for i, u in enumerate(urls)
    }
    return urls, pages


def _processed(result):
    return [i.url for i in result.items]


def test_repeated_capped_runs_cover_every_listed_report(conn):
    urls, pages = _many(6)
    web = site(**{LISTING: listing(*urls)}, **pages)
    inst = institution(max_documents_per_run=5)
    first = run(conn, inst, web)
    assert _processed(first) == urls[:5]
    second = run(conn, inst, web)
    assert _processed(second)[0] == urls[5]  # never attempted before: first in line
    assert len(second.items) == 5  # the per-run cap still holds
    assert outcomes(second)[0] == "new"
    assert all(pub_row(conn, u) is not None for u in urls)


def test_a_new_report_appended_after_the_cap_is_fetched_on_the_next_run(conn):
    urls, pages = _many(6)
    inst = institution(max_documents_per_run=5)
    run(conn, inst, site(**{LISTING: listing(*urls[:5])}, **pages))
    web = site(**{LISTING: listing(*urls)}, **pages)  # a sixth report is published
    result = run(conn, inst, web)
    assert _processed(result)[0] == urls[5]
    assert outcomes(result)[0] == "new"


def test_rotation_visits_the_least_recently_attempted_first_and_loops_around(conn):
    urls, pages = _many(4)
    web = site(**{LISTING: listing(*urls)}, **pages)
    inst = institution(max_documents_per_run=2)
    order = [_processed(run(conn, inst, web)) for _ in range(4)]
    assert order == [urls[0:2], urls[2:4], urls[0:2], urls[2:4]]


def test_a_rotated_report_that_changed_is_still_revision_checked(conn):
    urls, pages = _many(4)
    inst = institution(max_documents_per_run=2)
    run(conn, inst, site(**{LISTING: listing(*urls)}, **pages))
    run(conn, inst, site(**{LISTING: listing(*urls)}, **pages))  # second pair, all stored
    _, revised = _many(4, changed=(0,))
    result = run(conn, inst, site(**{LISTING: listing(*urls)}, **revised))
    assert _processed(result) == urls[0:2]
    assert outcomes(result) == ["updated", "unchanged"]
    assert conn.execute("SELECT COUNT(*) FROM research_document_version WHERE publication_id="
                        "(SELECT id FROM research_publication WHERE canonical_url=?)",
                        (urls[0],)).fetchone()[0] == 2  # fmt: skip


def test_a_report_that_always_fails_does_not_starve_the_others(conn):
    urls, pages = _many(4)
    del pages[urls[0]]  # r0 is listed but always 404
    web = site(**{LISTING: listing(*urls)}, **pages)
    inst = institution(max_documents_per_run=2)
    seen = set()
    for _ in range(3):
        seen |= {i.url for i in run(conn, inst, web).items if i.outcome != "failed"}
    assert seen == set(urls[1:])


def test_rotation_never_exceeds_the_cap_or_a_lower_limit(conn):
    urls, pages = _many(7)
    web = site(**{LISTING: listing(*urls)}, **pages)
    inst = institution(max_documents_per_run=3)
    assert [len(run(conn, inst, web, limit=n).items) for n in (None, 2, 99, 1)] == [3, 2, 3, 1]


def test_a_dry_run_does_not_move_the_rotation(conn):
    urls, pages = _many(4)
    web = site(**{LISTING: listing(*urls)}, **pages)
    inst = institution(max_documents_per_run=2, review_status="needs_review")
    approved = institution(max_documents_per_run=2)
    run(conn, inst, web, dry_run=True)
    assert _processed(run(conn, approved, web)) == urls[0:2]


def test_other_institutions_do_not_influence_the_rotation(conn):
    urls, pages = _many(4)
    web = site(**{LISTING: listing(*urls)}, **pages)
    other = institution("other_bank", max_documents_per_run=2)
    mine = institution(max_documents_per_run=2)
    run(conn, other, web)
    assert _processed(run(conn, mine, web)) == urls[0:2]

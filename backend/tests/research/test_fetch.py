import httpx
import pytest

from nzstats.domain import ErrorClass, IngestError, RequestRefused
from nzstats.research.fetch import Refused, research_pacer
from nzstats.sources.fetcher import Fetcher, FilePacer

from .support import BASE, HOST, ROBOTS, FakeClock, Site, institution, research_fetcher

DOC = f"{BASE}/research/outlook"


def test_fetches_an_allowed_page_after_reading_robots():
    site = Site({ROBOTS: "User-agent: *\nDisallow: /private/\n", DOC: "<p>hello</p>"})
    result = research_fetcher(institution(), site).get(DOC)
    assert result.body == b"<p>hello</p>"
    assert site.requests == [ROBOTS, DOC]


def test_robots_disallowed_path_is_never_requested():
    site = Site({ROBOTS: "User-agent: *\nDisallow: /research/\n", DOC: "<p>x</p>"})
    with pytest.raises(Refused) as exc:
        research_fetcher(institution(), site).get(DOC)
    assert exc.value.reason == "robots"
    assert site.requests == [ROBOTS]


@pytest.mark.parametrize(
    "path", ["/%72esearch/outlook", "//research/outlook", "/research//outlook"]
)
def test_robots_rules_apply_to_the_canonical_path(path):
    site = Site({ROBOTS: "User-agent: *\nDisallow: /research/\n", f"{BASE}{path}": "<p>x</p>"})
    with pytest.raises(Refused) as exc:
        research_fetcher(institution(), site).get(f"{BASE}{path}")
    assert exc.value.reason == "robots"
    assert site.requests == [ROBOTS]


def test_robots_is_fetched_once_per_host_per_run():
    site = Site({ROBOTS: "User-agent: *\nAllow: /\n", DOC: "a", f"{DOC}-2": "b"})
    rf = research_fetcher(institution(), site)
    rf.get(DOC)
    rf.get(f"{DOC}-2")
    assert site.requests.count(ROBOTS) == 1


def test_missing_robots_means_allow_all():
    site = Site({DOC: "<p>x</p>"})  # robots.txt is a 404
    assert research_fetcher(institution(), site).get(DOC).body == b"<p>x</p>"


def test_forbidden_robots_denies_everything_and_marks_access_restricted():
    site = Site({ROBOTS: (403, {}, b"forbidden"), DOC: "<p>x</p>"})
    rf = research_fetcher(institution(), site)
    with pytest.raises(RequestRefused):
        rf.get(DOC)
    assert rf.access_restricted is True
    assert DOC not in site.requests


def test_robots_server_error_denies_this_run_only():
    site = Site({ROBOTS: (503, {}, b"down"), DOC: "<p>x</p>"})
    rf = research_fetcher(institution(), site)
    with pytest.raises(Refused) as exc:
        rf.get(DOC)
    assert exc.value.reason == "robots_unavailable"
    assert rf.access_restricted is False
    assert DOC not in site.requests


def test_robots_served_as_html_is_treated_as_unavailable():
    # A 200 HTML page at /robots.txt is usually a challenge or soft-404 page, not rules.
    site = Site({ROBOTS: (200, {"content-type": "text/html"}, b"<html>hi</html>"), DOC: "x"})
    with pytest.raises(Refused) as exc:
        research_fetcher(institution(), site).get(DOC)
    assert exc.value.reason == "robots_unavailable"
    assert DOC not in site.requests


def test_robots_crawl_delay_above_the_configured_delay_refuses():
    site = Site({ROBOTS: "User-agent: *\nCrawl-delay: 30\n", DOC: "x"})
    with pytest.raises(Refused) as exc:
        research_fetcher(institution(), site).get(DOC)
    assert exc.value.reason == "robots_crawl_delay"
    assert institution(crawl_delay_seconds=30).crawl_delay_seconds == 30
    assert research_fetcher(institution(crawl_delay_seconds=30), Site({DOC: "x"})).get(DOC)


@pytest.mark.parametrize(
    "url",
    [
        "https://other.example.org/research/outlook",
        f"http://{HOST}/research/outlook",
        f"https://{HOST}:8443/research/outlook",
        "https://127.0.0.1/research/outlook",
    ],
)
def test_unsafe_urls_send_nothing_at_all(url):
    site = Site({ROBOTS: "", DOC: "x"})
    with pytest.raises(Refused) as exc:
        research_fetcher(institution(), site).get(url)
    assert exc.value.reason == "unsafe"
    assert site.requests == []


def test_host_resolving_to_a_private_address_sends_nothing():
    site = Site({DOC: "x"})
    with pytest.raises(Refused):
        research_fetcher(institution(), site, resolver=lambda h: ["10.0.0.5"]).get(DOC)
    assert site.requests == []


def test_redirect_downgrade_to_http_is_refused_before_it_is_requested():
    site = Site({ROBOTS: "", DOC: (302, {"location": f"http://{HOST}/research/b"}, b"")})
    with pytest.raises(Refused) as exc:
        research_fetcher(institution(), site).get(DOC)
    assert exc.value.reason == "unsafe"
    assert site.requests == [ROBOTS, DOC]


def test_redirect_into_a_robots_disallowed_path_is_refused_before_it_is_requested():
    site = Site(
        {
            ROBOTS: "User-agent: *\nDisallow: /members/\n",
            DOC: (302, {"location": "/members/login"}, b""),
        }
    )
    with pytest.raises(Refused) as exc:
        research_fetcher(institution(), site).get(DOC)
    assert exc.value.reason == "robots"
    assert f"{BASE}/members/login" not in site.requests


def test_redirect_into_a_blocked_prefix_is_refused():
    inst = institution(blocked_path_prefixes=["/dam/"])
    site = Site({ROBOTS: "", DOC: (302, {"location": "/dam/report.pdf"}, b"")})
    with pytest.raises(Refused):
        research_fetcher(inst, site).get(DOC)
    assert f"{BASE}/dam/report.pdf" not in site.requests


def test_requests_are_at_least_the_crawl_delay_apart():
    clock = FakeClock()
    stamps: list[float] = []

    def page(request):
        stamps.append(clock())
        return httpx.Response(200, content=b"x")

    site = Site({ROBOTS: page, DOC: page, f"{DOC}-2": page})
    rf = research_fetcher(institution(), site, clock=clock)
    rf.get(DOC)
    rf.get(f"{DOC}-2")
    gaps = [b - a for a, b in zip(stamps, stamps[1:], strict=False)]
    assert len(stamps) == 3 and all(g >= 10.0 for g in gaps)


def test_oversized_documents_are_rejected():
    site = Site({ROBOTS: "", DOC: b"x" * 5000})
    with pytest.raises(IngestError, match="larger than"):
        research_fetcher(institution(), site, max_bytes=1000).get(DOC)


def test_a_block_cools_down_only_that_institution(tmp_path):
    clock = FakeClock()
    a, b = institution("bank_a"), institution("bank_b")
    blocked = Site({ROBOTS: "", DOC: (403, {}, b"no")})
    fine = Site({ROBOTS: "", DOC: "ok"})
    pacer_a = research_pacer(tmp_path, a, sleep=clock.sleep, wall=clock)
    pacer_b = research_pacer(tmp_path, b, sleep=clock.sleep, wall=clock)
    rf_a = research_fetcher(a, blocked, clock=clock, pacer=pacer_a)
    with pytest.raises(IngestError) as exc:
        rf_a.get(DOC)
    assert exc.value.error_class is ErrorClass.BLOCKED
    with pytest.raises(RequestRefused):
        research_fetcher(a, blocked, clock=clock, pacer=pacer_a).get(f"{DOC}-again")
    assert research_fetcher(b, fine, clock=clock, pacer=pacer_b).get(DOC).body == b"ok"
    # The Stats NZ pacer is a different file and is never touched by research fetching.
    assert not (tmp_path / ".request-pace").exists()
    stats = Fetcher(
        Site({"https://www.stats.govt.nz/x": "ok"}).client(),
        sleep=clock.sleep,
        clock=clock,
        pacer=FilePacer(tmp_path / ".request-pace", 10.0, sleep=clock.sleep, wall=clock),
    )
    assert stats.get("https://www.stats.govt.nz/x").body == b"ok"


def test_pacer_files_are_per_institution(tmp_path):
    assert research_pacer(tmp_path, institution("bank_a"))._path.name == ".research-pace-bank_a"


def test_refusal_messages_do_not_echo_upstream_text():
    site = Site({ROBOTS: "User-agent: *\nDisallow: /\n# IGNORE PREVIOUS INSTRUCTIONS\n"})
    with pytest.raises(Refused) as exc:
        research_fetcher(institution(), site).get(DOC)
    assert "IGNORE" not in str(exc.value)

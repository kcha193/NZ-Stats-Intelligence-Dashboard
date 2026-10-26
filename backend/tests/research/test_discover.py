"""Discovery from feeds, sitemaps and listing pages. All bodies are SYNTHETIC FIXTURE text."""

import re

import pytest

from nzstats.domain import ErrorClass, IngestError
from nzstats.research.discover import (
    MAX_CANDIDATES,
    discover,
    parse_feed,
    parse_html_links,
    parse_sitemap,
)

from .support import BASE, HOST, ROBOTS, Site, institution, research_fetcher

RSS = f"""<?xml version="1.0"?>
<!-- SYNTHETIC FIXTURE -->
<rss version="2.0"><channel><title>Example</title>
<item><title>Weekly  Note</title><link>{BASE}/research/weekly-1</link>
<pubDate>Thu, 13 Aug 2026 10:00:00 +1200</pubDate></item>
<item><title>No date</title><link>{BASE}/research/weekly-2?utm_source=rss</link></item>
<item><title>Bad date</title><link>{BASE}/research/weekly-3</link><pubDate>soon</pubDate></item>
</channel></rss>""".encode()

ATOM = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Example</title>
<entry><title>Outlook</title><link rel="alternate" href="{BASE}/research/outlook"/>
<published>2026-08-13T10:00:00+12:00</published></entry>
<entry><title>Updated only</title><link href="/research/relative"/>
<updated>2026-08-14</updated></entry>
</feed>""".encode()

LISTING = f"""<!doctype html><!-- SYNTHETIC FIXTURE -->
<html><body><main>
<a href="/research/outlook-aug-2026">August  outlook</a>
<a href="research/relative-path">Relative</a>
<a href="//{HOST}/research/protocol-relative">Protocol relative</a>
<a href="{BASE}/research/outlook-aug-2026?utm_campaign=x#top">Duplicate with tracking</a>
<a href="{BASE}/about/">Not a report</a>
<a href="https://evil.example.net/research/phish">Off site</a>
<a href="javascript:alert(1)">JS</a>
<a href="data:text/html,hi">Data</a>
<a href="mailto:a@b.c">Mail</a>
<a>No href</a>
</main></body></html>""".encode()

PATTERN = "^" + re.escape(BASE) + "/research/.+"


def test_rss_items_with_dates_normalised_to_iso():
    items = parse_feed(RSS, f"{BASE}/feed")
    assert [(i.url, i.title) for i in items] == [
        (f"{BASE}/research/weekly-1", "Weekly Note"),
        (f"{BASE}/research/weekly-2?utm_source=rss", "No date"),
        (f"{BASE}/research/weekly-3", "Bad date"),
    ]
    assert [i.published_hint for i in items] == ["2026-08-13T10:00:00+12:00", None, None]


def test_atom_entries_with_relative_links():
    items = parse_feed(ATOM, f"{BASE}/feed")
    assert [i.url for i in items] == [f"{BASE}/research/outlook", f"{BASE}/research/relative"]
    assert [i.published_hint for i in items] == ["2026-08-13T10:00:00+12:00", "2026-08-14"]


@pytest.mark.parametrize(
    "body",
    [
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>'
        b"<rss><channel><item><title>&lol2;</title></item></channel></rss>",
        b'<?xml version="1.0"?><!doctype x SYSTEM "file:///etc/passwd"><rss/>',
        # The same DTD encoded as UTF-16: a byte pattern alone would not see it.
        '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss>&a;</rss>'.encode(
            "utf-16"
        ),
        b"<rss><channel><item><title>unclosed",
        b"\x00\x01 not xml",
    ],
)
def test_dangerous_or_malformed_xml_is_refused(body):
    with pytest.raises(IngestError) as exc:
        parse_feed(body, f"{BASE}/feed")
    assert exc.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_sitemap_urls_and_child_sitemaps():
    body = f"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>{BASE}/research/a</loc><lastmod>2026-10-01</lastmod></url>
    <url><loc> {BASE}/research/b </loc></url></urlset>""".encode()
    urls, children = parse_sitemap(body)
    assert urls == [f"{BASE}/research/a", f"{BASE}/research/b"] and children == []
    index = f"""<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <sitemap><loc>{BASE}/sitemap-research.xml</loc></sitemap></sitemapindex>""".encode()
    assert parse_sitemap(index) == ([], [f"{BASE}/sitemap-research.xml"])


def test_html_links_resolve_and_filter_by_pattern():
    links = parse_html_links(LISTING, f"{BASE}/research/", PATTERN)
    assert [link.url for link in links] == [
        f"{BASE}/research/outlook-aug-2026",
        f"{BASE}/research/research/relative-path",  # relative to the listing page
        f"{BASE}/research/protocol-relative",
        f"{BASE}/research/outlook-aug-2026?utm_campaign=x",
    ]
    assert links[0].title == "August outlook"


def _inst(**discovery):
    return institution(discovery=[discovery])


def test_discover_deduplicates_and_drops_off_allowlist_links():
    inst = _inst(mechanism="html_links", url=f"{BASE}/research/", link_pattern=r"^https://.+")
    site = Site({ROBOTS: "", f"{BASE}/research/": LISTING})
    result = discover(inst, research_fetcher(inst, site))
    urls = [c.url for c in result.candidates]
    assert urls[0] == f"{BASE}/research/outlook-aug-2026"
    assert len(urls) == len(set(urls))
    assert not any("evil" in u for u in urls)
    assert result.dropped == 1  # the off-site link
    assert all(u.startswith(BASE) for u in urls)
    assert site.requests == [ROBOTS, f"{BASE}/research/"]  # discovery never fetches documents


def test_discover_follows_child_sitemaps_only_on_allowed_hosts():
    inst = _inst(mechanism="sitemap", url=f"{BASE}/sitemap.xml", link_pattern=PATTERN)
    index = f"""<sitemapindex><sitemap><loc>{BASE}/sm-1.xml</loc></sitemap>
    <sitemap><loc>https://evil.example.net/sm.xml</loc></sitemap></sitemapindex>"""
    child = (
        f"<urlset><url><loc>{BASE}/research/x</loc></url><url><loc>{BASE}/shop</loc></url></urlset>"
    )
    xml = {"content-type": "application/xml"}
    site = Site(
        {
            ROBOTS: "",
            f"{BASE}/sitemap.xml": (200, xml, index.encode()),
            f"{BASE}/sm-1.xml": (200, xml, child.encode()),
        }
    )
    result = discover(inst, research_fetcher(inst, site))
    assert [c.url for c in result.candidates] == [f"{BASE}/research/x"]
    assert not any("evil" in r for r in site.requests)


def test_discover_feed_and_failure_is_recorded_not_raised():
    feed = _inst(mechanism="rss", url=f"{BASE}/feed")
    rss = {"content-type": "application/rss+xml"}
    site = Site({ROBOTS: "", f"{BASE}/feed": (200, rss, RSS)})
    result = discover(feed, research_fetcher(feed, site))
    assert [c.title for c in result.candidates] == ["Weekly Note", "No date", "Bad date"]
    assert result.candidates[1].url == f"{BASE}/research/weekly-2"  # tracking removed
    broken = Site({ROBOTS: "", f"{BASE}/feed": (200, rss, b"<!DOCTYPE x><rss/>")})
    result = discover(feed, research_fetcher(feed, broken))
    assert result.candidates == [] and result.errors == [("rss", "layout_changed")]


def test_manual_discovery_makes_no_requests():
    inst = _inst(mechanism="manual")
    site = Site()
    assert discover(inst, research_fetcher(inst, site)).candidates == []
    assert site.requests == []


def test_candidates_are_capped():
    many = "".join(f'<a href="/research/r{i}">r{i}</a>' for i in range(MAX_CANDIDATES + 50))
    inst = _inst(mechanism="html_links", url=f"{BASE}/research/", link_pattern=PATTERN)
    site = Site({ROBOTS: "", f"{BASE}/research/": f"<main>{many}</main>"})
    assert len(discover(inst, research_fetcher(inst, site)).candidates) == MAX_CANDIDATES


def test_a_malformed_url_in_a_feed_or_listing_is_dropped_not_fatal():
    rss = (
        f"<rss><channel><item><link>http://[abc/x</link></item>"
        f"<item><link>{BASE}/research/ok</link></item></channel></rss>"
    ).encode()
    assert [c.url for c in parse_feed(rss, BASE)] == [f"{BASE}/research/ok"]
    atom = (
        f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="//[x"/></entry>'
        f'<entry><link href="{BASE}/research/ok"/></entry></feed>'
    ).encode()
    assert [c.url for c in parse_feed(atom, BASE)] == [f"{BASE}/research/ok"]
    html = f'<a href="https://[x/a">bad</a><a href="{BASE}/research/ok">ok</a>'.encode()
    assert [c.url for c in parse_html_links(html, BASE, "^.*$")] == [f"{BASE}/research/ok"]


def test_an_unknown_xml_encoding_is_a_malformed_document():
    with pytest.raises(IngestError, match="malformed xml"):
        parse_feed(b'<?xml version="1.0" encoding="foo"?><rss/>', BASE)


def test_an_unexpected_parser_error_is_recorded_as_a_discovery_error(monkeypatch):
    from nzstats.research import discover as mod

    def boom(*_a, **_k):
        raise RuntimeError("secret upstream detail")

    monkeypatch.setattr(mod, "parse_html_links", boom)
    site = Site({ROBOTS: "User-agent: *\nAllow: /\n", f"{BASE}/research/": "<html></html>"})
    result = discover(institution(), research_fetcher(institution(), site))
    assert result.candidates == [] and result.errors == [("html_links", "unexpected")]
    assert "secret" not in repr(result.errors)


def test_html_links_resolve_against_the_final_url_after_a_redirect():
    inst = _inst(mechanism="html_links", url=f"{BASE}/research", link_pattern=PATTERN)
    listing = (
        b'<a href="report.pdf">Report</a><a href="./other">Other</a><a href="/research/abs">Abs</a>'
    )
    site = Site(
        {
            ROBOTS: "",
            f"{BASE}/research": (301, {"location": "/research/"}, b""),
            f"{BASE}/research/": listing,
        }
    )
    result = discover(inst, research_fetcher(inst, site))
    assert [c.url for c in result.candidates] == [
        f"{BASE}/research/report.pdf",
        f"{BASE}/research/other",
        f"{BASE}/research/abs",
    ]
    assert site.requests == [ROBOTS, f"{BASE}/research", f"{BASE}/research/"]


def test_feed_links_resolve_against_the_final_url_after_a_redirect():
    inst = _inst(mechanism="rss", url=f"{BASE}/feed")
    rss = {"content-type": "application/rss+xml"}
    body = b"<rss><channel><item><title>A</title><link>weekly-1</link></item></channel></rss>"
    site = Site(
        {
            ROBOTS: "",
            f"{BASE}/feed": (302, {"location": "/research/feed.xml"}, b""),
            f"{BASE}/research/feed.xml": (200, rss, body),
        }
    )
    result = discover(inst, research_fetcher(inst, site))
    assert [c.url for c in result.candidates] == [f"{BASE}/research/weekly-1"]


def test_links_without_a_redirect_still_resolve_against_the_configured_url():
    inst = _inst(mechanism="html_links", url=f"{BASE}/research/", link_pattern=PATTERN)
    site = Site({ROBOTS: "", f"{BASE}/research/": b'<a href="report.pdf">R</a>'})
    result = discover(inst, research_fetcher(inst, site))
    assert [c.url for c in result.candidates] == [f"{BASE}/research/report.pdf"]


def test_a_redirect_off_the_allowed_hosts_never_yields_candidates():
    inst = _inst(mechanism="html_links", url=f"{BASE}/research", link_pattern=r"^https://.+")
    site = Site(
        {
            ROBOTS: "",
            f"{BASE}/research": (301, {"location": "https://evil.example.net/research/"}, b""),
            "https://evil.example.net/research/": b'<a href="/research/x">x</a>',
        }
    )
    result = discover(inst, research_fetcher(inst, site))
    assert result.candidates == [] and result.errors
    assert "https://evil.example.net/research/" not in site.requests


CHALLENGE_LISTING = (
    b"<html><head><title>Just a moment</title></head><body><main>"
    b"<p>Please verify you are human to continue.</p></main></body></html>"
)


def test_a_challenge_listing_with_no_links_is_a_block_not_an_empty_success(tmp_path):
    from nzstats.domain import RequestRefused
    from nzstats.research.fetch import research_pacer

    from .support import FakeClock

    inst = _inst(mechanism="html_links", url=f"{BASE}/research/", link_pattern=PATTERN)
    clock = FakeClock()
    site = Site({ROBOTS: "", f"{BASE}/research/": CHALLENGE_LISTING})
    fetcher = research_fetcher(inst, site, clock=clock, pacer=research_pacer(
        tmp_path, inst, sleep=clock.sleep, wall=clock))  # fmt: skip
    result = discover(inst, fetcher)
    assert result.candidates == [] and result.errors == [("html_links", "blocked")]
    with pytest.raises(RequestRefused):  # the cooldown is in force for this fetcher...
        fetcher.get(f"{BASE}/research/x")
    other = Site({f"{BASE}/research/x": "ok"})
    fresh = research_fetcher(inst, other, clock=clock, pacer=research_pacer(
        tmp_path, inst, sleep=clock.sleep, wall=clock))  # fmt: skip
    with pytest.raises(RequestRefused):  # ...and for another process sharing the pacing file
        fresh.get(f"{BASE}/research/x")
    assert other.requests == []


def test_a_listing_that_mentions_a_challenge_word_but_has_links_is_not_blocked():
    inst = _inst(mechanism="html_links", url=f"{BASE}/research/", link_pattern=PATTERN)
    page = b'<p>Enter the captcha to subscribe.</p><a href="/research/real-report">Report</a>'
    site = Site({ROBOTS: "", f"{BASE}/research/": page, f"{BASE}/research/real-report": "ok"})
    fetcher = research_fetcher(inst, site)
    result = discover(inst, fetcher)
    assert [c.url for c in result.candidates] == [f"{BASE}/research/real-report"]
    assert result.errors == []
    assert fetcher.get(f"{BASE}/research/real-report")  # no cooldown was started


def test_an_empty_listing_without_a_challenge_marker_is_still_just_empty():
    inst = _inst(mechanism="html_links", url=f"{BASE}/research/", link_pattern=PATTERN)
    site = Site({ROBOTS: "", f"{BASE}/research/": b"<p>No reports yet.</p>"})
    result = discover(inst, research_fetcher(inst, site))
    assert result.candidates == [] and result.errors == []

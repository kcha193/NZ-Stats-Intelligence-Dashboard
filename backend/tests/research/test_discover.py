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

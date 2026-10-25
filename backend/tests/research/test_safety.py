import httpx
import pytest

from nzstats.research.safety import (
    ALLOW_ALL,
    DENY_ALL,
    HostPolicy,
    PinnedTransport,
    RobotsRules,
    UnsafeUrl,
    canonical_path,
    normalise_url,
)

AGENT = "NZStatsDashboard"


def public(host):
    return ["93.184.216.34"]


def policy(hosts=("www.anz.co.nz",), **kw):
    return HostPolicy(allowed_hosts=hosts, resolver=kw.pop("resolver", public), **kw)


def test_accepts_a_plain_https_url_on_an_allowed_host():
    assert (
        policy().check("https://www.anz.co.nz/about-us/x.pdf")
        == "https://www.anz.co.nz/about-us/x.pdf"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://www.anz.co.nz/a",  # not https
        "ftp://www.anz.co.nz/a",
        "//www.anz.co.nz/a",  # no scheme
        "https://user:pw@www.anz.co.nz/a",  # userinfo
        "https://www.anz.co.nz@evil.test/a",  # userinfo trick
        "https://www.anz.co.nz:8443/a",  # port
        "https://www.anz.co.nz.evil.test/a",  # look-alike suffix
        "https://evil-www.anz.co.nz/a",
        "https://anz.co.nz/a",  # not on the list
        "https://127.0.0.1/a",
        "https://localhost/a",
        "https://[::1]/a",
        "https://169.254.169.254/latest/meta-data",
        "https://2130706433/a",  # decimal IP
        "https://www.anz.co.nz/a\r\nHost: evil",  # header injection
        "https://www.anz.co.nz/a\\..\\b",
        "javascript:alert(1)",
        "data:text/html,hi",
        "",
    ],
)
def test_rejects_unsafe_urls(url):
    with pytest.raises(UnsafeUrl):
        policy(hosts=("www.anz.co.nz", "localhost")).check(url)


def test_host_match_is_case_and_trailing_dot_insensitive_but_exact():
    assert policy().check("https://WWW.ANZ.CO.NZ./a") == "https://www.anz.co.nz/a"


@pytest.mark.parametrize(
    "path",
    ["/nz/%70rivate/x", "/nz/Private/x", "/nz//private/x", "/nz/%50rivate/x", "//nz/private/x"],
)
def test_blocked_prefixes_cannot_be_bypassed_by_encoding_case_or_double_slashes(path):
    p = policy(hosts=("www.deloitte.com",), blocked_path_prefixes=("/nz/private/",))
    with pytest.raises(UnsafeUrl, match="path"):
        p.check(f"https://www.deloitte.com{path}")


def test_allowed_prefixes_see_the_canonical_path_too():
    p = policy(hosts=("www.deloitte.com",), allowed_path_prefixes=("/nz/",))
    assert p.check("https://www.deloitte.com/%6ez/en/x.html")  # %6e is "n"
    with pytest.raises(UnsafeUrl, match="path"):
        p.check("https://www.deloitte.com//au/x.html")


def test_canonical_path_decodes_only_unreserved_characters():
    assert canonical_path("/a/%70b//c%2fd%7e/%e2%82%ac") == "/a/pb/c%2Fd~/%E2%82%AC"


def test_path_prefix_allowlist_and_blocklist():
    p = policy(hosts=("www.deloitte.com",), allowed_path_prefixes=("/nz/",),
               blocked_path_prefixes=("/nz/private/",))  # fmt: skip
    assert p.check("https://www.deloitte.com/nz/en/x.html")
    with pytest.raises(UnsafeUrl, match="path"):
        p.check("https://www.deloitte.com/au/en/x.html")
    with pytest.raises(UnsafeUrl, match="path"):
        p.check("https://www.deloitte.com/nz/private/x.html")
    with pytest.raises(UnsafeUrl, match="path"):
        p.check("https://www.deloitte.com/nz/%2e%2e/au/x.html")  # traversal out of the prefix
    with pytest.raises(UnsafeUrl, match="path"):
        p.check("https://www.deloitte.com/nz/../au/x.html")


def test_resolved_private_or_loopback_addresses_are_rejected():
    for addr in ("10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.1", "::1", "fd00::1"):
        with pytest.raises(UnsafeUrl, match="address"):
            policy(resolver=lambda h, a=addr: [a]).check("https://www.anz.co.nz/a")
    with pytest.raises(UnsafeUrl, match="address"):  # one bad record among good ones
        policy(resolver=lambda h: ["93.184.216.34", "10.0.0.5"]).check("https://www.anz.co.nz/a")


def test_unresolvable_host_is_rejected_not_raised_as_oserror():
    def boom(host):
        raise OSError("no such host")

    with pytest.raises(UnsafeUrl, match="resolve"):
        policy(resolver=boom).check("https://www.anz.co.nz/a")


def test_normalise_url_gives_a_stable_identity():
    a = normalise_url("HTTPS://WWW.ANZ.CO.NZ:443/a/b/?utm_source=x&id=2&fbclid=z#top")
    b = normalise_url("https://www.anz.co.nz/a/b?id=2")
    assert a == b == "https://www.anz.co.nz/a/b?id=2"
    assert normalise_url("https://www.anz.co.nz/") == "https://www.anz.co.nz/"
    assert normalise_url("https://x.test/a?b=2&a=1") == normalise_url("https://x.test/a?a=1&b=2")


TREASURY = """
# reconstructed from the 2026-10-25 probe summary
User-agent: *
Allow: /core/*.css$
Allow: /core/*.js$
Disallow: /core/
Disallow: /profiles/
Disallow: /README.md
Disallow: /admin/
Disallow: /search/
Disallow: /publications/search
"""

ASB = """User-agent: *
Disallow: /ASBWeb/Javascript/
Disallow: /content/dam/asb/documents/
Disallow: /content/asb/forms/

User-agent: HTTrack
User-agent: Wget
Disallow: /
"""


def test_treasury_rules():
    r = RobotsRules.parse(TREASURY, AGENT)
    assert r.allowed("/publications/budget-2026")
    assert not r.allowed("/publications/search")
    assert not r.allowed("/publications/search?q=gdp")
    assert r.allowed("/core/misc/site.css")  # longer Allow beats Disallow
    assert not r.allowed("/core/misc/x.php")
    assert not r.allowed("/admin/config")


def test_asb_rules_block_report_pdfs_but_not_report_pages():
    r = RobotsRules.parse(ASB, AGENT)
    assert not r.allowed(
        "/content/dam/asb/documents/reports/economic-weekly/economicweekly_190218.pdf"
    )
    assert r.allowed("/documents/economic-research/economic-weekly/one-up.html")


def test_named_bot_group_does_not_apply_to_us_but_a_group_naming_us_does():
    assert RobotsRules.parse(ASB, AGENT).allowed("/anything")
    text = "User-agent: nzstatsdashboard\nDisallow: /private\n\nUser-agent: *\nDisallow: /\n"
    r = RobotsRules.parse(text, AGENT)
    assert r.allowed("/public") and not r.allowed("/private/x")  # specific group beats *


def test_allow_wins_ties_and_longest_pattern_wins():
    r = RobotsRules.parse("User-agent: *\nDisallow: /a\nAllow: /a\n", AGENT)
    assert r.allowed("/a/b")
    r = RobotsRules.parse("User-agent: *\nAllow: /a\nDisallow: /a/b\n", AGENT)
    assert r.allowed("/a/c") and not r.allowed("/a/b/c")


def test_wildcards_and_end_anchor():
    r = RobotsRules.parse("User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp*/x\n", AGENT)
    assert not r.allowed("/a/b.pdf")
    assert r.allowed("/a/b.pdf?download=1")  # `$` anchors the end
    assert not r.allowed("/tmp-1/x")
    assert r.allowed("/b.pdfx")


def test_empty_disallow_allows_everything_and_crlf_bom_comments_are_handled():
    assert RobotsRules.parse("User-agent: *\nDisallow:\n", AGENT).allowed("/x")
    text = "﻿User-agent: *   # everyone\r\nDisallow: /no # comment\r\nCrawl-delay: 20\r\n"
    r = RobotsRules.parse(text, AGENT)
    assert not r.allowed("/no/x") and r.allowed("/yes") and r.crawl_delay == 20.0


def test_no_applicable_group_means_allowed_and_garbage_does_not_crash():
    assert RobotsRules.parse("User-agent: SomeoneElse\nDisallow: /\n", AGENT).allowed("/x")
    assert RobotsRules.parse("<html>Access Denied</html>\x00\x01", AGENT).allowed("/x")
    assert RobotsRules.parse("", AGENT).allowed("/x")


def test_oversized_robots_text_is_truncated_not_trusted_past_the_cap():
    text = "User-agent: *\n" + "Disallow: /z\n" * 100_000 + "Disallow: /late\n"
    r = RobotsRules.parse(text, AGENT)  # must finish quickly and not raise
    assert not r.allowed("/z")


def test_constants():
    assert ALLOW_ALL.allowed("/x") and not DENY_ALL.allowed("/x") and not DENY_ALL.allowed("/")


def test_encoded_robots_patterns_and_prefixes_match_the_canonical_target():
    rules = RobotsRules.parse("User-agent: *\nDisallow: /%72esearch/\nDisallow: /a//b\n", AGENT)
    assert not rules.allowed(canonical_path("/research/x"))
    assert not rules.allowed(canonical_path("/%72esearch/x"))
    assert not rules.allowed(canonical_path("/a/b"))
    p = policy(hosts=("www.deloitte.com",), blocked_path_prefixes=("/nz/%70rivate/",))
    with pytest.raises(UnsafeUrl, match="path"):
        p.check("https://www.deloitte.com/nz/private/x")


@pytest.mark.parametrize(
    "address",
    [
        "64:ff9b::7f00:1",
        "::127.0.0.1",
        "fec0::1",
        "2002:7f00:1::1",
        "2002:a00:1::1",
        "::ffff:10.0.0.1",
    ],
)
def test_addresses_that_embed_or_alias_private_space_are_not_public(address):
    p = policy(resolver=lambda host: [address])
    with pytest.raises(UnsafeUrl, match="non-public"):
        p.check("https://www.anz.co.nz/a")


def test_a_real_public_ipv6_address_is_still_accepted():
    assert policy(resolver=lambda host: ["2606:4700::6810:84e5"]).check("https://www.anz.co.nz/a")


class _Inner(httpx.BaseTransport):
    def __init__(self):
        self.seen: list[httpx.Request] = []

    def handle_request(self, request):
        self.seen.append(request)
        return httpx.Response(200, content=b"ok", request=request)


def _client(resolver):
    inner = _Inner()
    client = httpx.Client(transport=PinnedTransport(resolver, inner), trust_env=False)
    return client, inner


def test_the_connection_is_pinned_to_the_validated_address_with_the_original_name():
    client, inner = _client(lambda host: ["93.184.216.34"])
    assert client.get("https://www.anz.co.nz/a?x=1").content == b"ok"
    sent = inner.seen[0]
    assert sent.url.host == "93.184.216.34" and sent.url.path == "/a" and sent.url.query == b"x=1"
    assert sent.headers["host"] == "www.anz.co.nz"
    assert sent.extensions["sni_hostname"] == "www.anz.co.nz"


def test_a_name_that_rebinds_to_a_private_address_is_refused_at_connect_time():
    answers = iter([["93.184.216.34"], ["127.0.0.1"]])
    client, inner = _client(lambda host: next(answers))
    policy_check = policy(resolver=lambda host: ["93.184.216.34"]).check("https://www.anz.co.nz/a")
    assert policy_check  # the early check saw a public address...
    client.get("https://www.anz.co.nz/a")  # ...and so did the first connect
    with pytest.raises(httpx.ConnectError):
        client.get("https://www.anz.co.nz/a")  # but the second resolution is private
    assert len(inner.seen) == 1


def test_an_unresolvable_name_is_a_connect_error():
    def gone(host):
        raise OSError("no such host")

    client, inner = _client(gone)
    with pytest.raises(httpx.ConnectError):
        client.get("https://www.anz.co.nz/a")
    assert inner.seen == []

"""Find candidate report URLs from an institution's configured discovery mechanisms.

Discovery fetches only feeds, sitemaps and listing pages, never documents. XML is refused outright if
it declares a DOCTYPE or entities (no entity expansion, no external references). Every candidate must
pass the institution's host and path policy; candidates are deduplicated by normalised URL (tracking
parameters removed) and capped. Sitemap `lastmod` is a modification time, not a publication date, so
it is not used as a date hint. robots.txt is enforced when a document is actually fetched.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin
from xml.parsers import expat

from nzstats.domain import ErrorClass, IngestError
from nzstats.research.extract import clean_text
from nzstats.research.fetch import ResearchFetcher
from nzstats.research.registry import Discovery, Institution, Mechanism
from nzstats.research.safety import HostPolicy, UnsafeUrl
from nzstats.research.validate import MARKER_WINDOW, looks_like_challenge

log = logging.getLogger(__name__)

MAX_CANDIDATES = 200
MAX_CHILD_SITEMAPS = 5
MAX_URL_CHARS = 2048
MAX_TITLE_CHARS = 300
_XML_DECL = re.compile(rb"<!\s*(doctype|entity)", re.IGNORECASE)
_SCHEMES = ("https:", "http:", "//", "/")
FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/xml", "text/xml")
SITEMAP_TYPES = ("application/xml", "text/xml")
HTML_TYPES = ("text/html", "application/xhtml+xml")


@dataclass(frozen=True)
class Candidate:
    url: str  # normalised
    title: str | None = None
    published_hint: str | None = None
    series: str | None = None


@dataclass
class DiscoveryResult:
    candidates: list[Candidate] = field(default_factory=list)
    dropped: int = 0  # links outside the host/path policy
    errors: list[tuple[str, str]] = field(default_factory=list)  # (mechanism, error class)


def _title(text: str | None) -> str | None:
    if not text:
        return None
    return " ".join(clean_text(text).split())[:MAX_TITLE_CHARS] or None


class _DtdRefused(Exception):
    pass


def _refuse(*_args: object) -> None:
    raise _DtdRefused


def _xml(body: bytes) -> ET.Element:
    def dtd() -> IngestError:
        return IngestError(ErrorClass.LAYOUT_CHANGED, "xml with a DOCTYPE or entity declaration")

    if _XML_DECL.search(body):  # cheap first check on the raw bytes
        raise dtd()
    # Then a pre-scan in which expat itself (after decoding, whatever the encoding) refuses any
    # DOCTYPE, entity declaration or external reference. Without a DTD nothing can be expanded.
    scanner = expat.ParserCreate()
    scanner.StartDoctypeDeclHandler = _refuse
    scanner.EntityDeclHandler = _refuse
    scanner.UnparsedEntityDeclHandler = _refuse
    scanner.ExternalEntityRefHandler = _refuse
    try:
        scanner.Parse(body, True)
    except _DtdRefused:
        raise dtd() from None
    except (expat.ExpatError, LookupError, ValueError):  # LookupError: an unknown declared encoding
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "malformed xml") from None
    try:
        return ET.fromstring(body)
    except (ET.ParseError, LookupError, ValueError):
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "malformed xml") from None


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _child_text(node: ET.Element, name: str) -> str | None:
    for child in node:
        if _local(child.tag) == name and child.text:
            return child.text.strip()
    return None


def _rss_date(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return parsedate_to_datetime(text).isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def _join(base_url: str, ref: str) -> str | None:
    """`urljoin`, or None for a reference it cannot parse (for example an invalid IPv6 literal)."""
    try:
        return urljoin(base_url, ref)
    except ValueError:
        return None


def parse_feed(body: bytes, base_url: str) -> list[Candidate]:
    """RSS 2.0 items or Atom entries, in feed order. URLs are absolute but not yet normalised."""
    root = _xml(body)
    out: list[Candidate] = []
    for node in root.iter():
        kind = _local(node.tag)
        if kind == "item":
            link = _child_text(node, "link")
            hint = _rss_date(_child_text(node, "pubdate"))
        elif kind == "entry":
            link = next(
                (
                    c.get("href")
                    for c in node
                    if _local(c.tag) == "link" and c.get("rel", "alternate") == "alternate"
                ),
                None,
            )
            hint = _child_text(node, "published") or _child_text(node, "updated")
        else:
            continue
        if link and (url := _join(base_url, link.strip())):
            out.append(Candidate(url, _title(_child_text(node, "title")), hint))
    return out


def parse_sitemap(body: bytes) -> tuple[list[str], list[str]]:
    """(page URLs, child sitemap URLs)."""
    root = _xml(body)
    urls, children = [], []
    for node in root:
        loc = _child_text(node, "loc")
        if not loc:
            continue
        (children if _local(node.tag) == "sitemap" else urls).append(loc.strip())
    return urls, children


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, list[str]]] = []
        self._open: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            self._open = None
            if href:
                self._open = []
                self.links.append((href.strip(), self._open))

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._open = None

    def handle_data(self, data: str) -> None:
        if self._open is not None and sum(map(len, self._open)) < MAX_TITLE_CHARS:
            self._open.append(data)


def parse_html_links(body: bytes, base_url: str, link_pattern: str) -> list[Candidate]:
    """Anchors whose resolved absolute URL matches `link_pattern`, in page order."""
    parser = _Links()
    parser.feed(body.decode("utf-8", errors="replace"))
    pattern = re.compile(link_pattern)
    out = []
    for href, text in parser.links:
        if len(href) > MAX_URL_CHARS or not href.lower().startswith(_SCHEMES) and ":" in href:
            continue  # javascript:, data:, mailto:, tel: ...
        joined = _join(base_url, href)
        url = joined.split("#", 1)[0] if joined else None
        if url and pattern.match(url):
            out.append(Candidate(url, _title("".join(text))))
    return out


def discover(inst: Institution, fetcher: ResearchFetcher) -> DiscoveryResult:
    result = DiscoveryResult()
    static = HostPolicy(
        inst.allowed_hosts,
        allowed_path_prefixes=inst.allowed_path_prefixes,
        blocked_path_prefixes=inst.blocked_path_prefixes,
        resolver=None,  # DNS is checked when a URL is actually fetched
    )
    seen: set[str] = set()

    def add(candidate: Candidate, series: str | None) -> None:
        if len(result.candidates) >= MAX_CANDIDATES:
            return
        try:
            url = static.check(candidate.url)
        except UnsafeUrl:
            result.dropped += 1
            return
        if url not in seen:
            seen.add(url)
            result.candidates.append(
                Candidate(url, candidate.title, candidate.published_hint, series)
            )

    for source in inst.discovery:
        if source.mechanism is Mechanism.MANUAL or not source.url:
            continue
        try:
            for candidate in _from(source, fetcher, static):
                add(candidate, source.series)
        except IngestError as exc:
            log.warning("discovery %s for %s failed: %s", source.mechanism.value, inst.key,
                        exc.error_class.value)  # fmt: skip
            result.errors.append((source.mechanism.value, exc.error_class.value))
        except (
            Exception
        ):  # a parser bug on hostile input is one failed mechanism, not an aborted run
            log.exception("discovery %s for %s crashed", source.mechanism.value, inst.key)
            result.errors.append((source.mechanism.value, ErrorClass.UNEXPECTED.value))
    return result


def _head(body: bytes) -> str:
    return body[: 4 * MARKER_WINDOW].decode("utf-8", errors="replace")[:MARKER_WINDOW]


def _from(source: Discovery, fetcher: ResearchFetcher, static: HostPolicy) -> list[Candidate]:
    assert source.url is not None
    # Relative links are resolved against the URL that actually served the page (`fetched.url`, after
    # any redirects), not the configured one.
    if source.mechanism is Mechanism.RSS:
        fetched = fetcher.get(source.url, expect=FEED_TYPES)
        return parse_feed(fetched.body, fetched.url)
    if source.mechanism is Mechanism.HTML_LINKS:
        fetched = fetcher.get(source.url, expect=HTML_TYPES)
        found = parse_html_links(fetched.body, fetched.url, source.link_pattern or "^$")
        if not found and looks_like_challenge(_head(fetched.body)):
            # An HTTP 200 bot-challenge page is not an empty listing: start the institution cooldown.
            fetcher.record_block()
            raise IngestError(ErrorClass.BLOCKED, "challenge_page", url=fetched.url)
        return found
    pattern = re.compile(source.link_pattern) if source.link_pattern else None
    urls, children = parse_sitemap(fetcher.get(source.url, expect=SITEMAP_TYPES).body)
    for child in children[:MAX_CHILD_SITEMAPS]:
        try:
            static.check(child)
        except UnsafeUrl:
            continue
        urls += parse_sitemap(fetcher.get(child, expect=SITEMAP_TYPES).body)[0]
    return [
        Candidate(u) for u in urls if len(u) <= MAX_URL_CHARS and (not pattern or pattern.match(u))
    ]

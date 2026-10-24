"""Check a built static site before it is deployed: assets, routing files, page metadata, and what must not be in it."""

from __future__ import annotations

import re
import tomllib
from html.parser import HTMLParser
from pathlib import Path

from nzstats.publish.validate import Report, validate_snapshot

REQUIRED = (
    "index.html", "404.html", "robots.txt", "_redirects", "data-not-found.json", "favicon.svg",
    "og-card.png", "data/v1/manifest.json",
)  # fmt: skip
FORBIDDEN_NAMES = re.compile(r"(\.map|\.db|\.sqlite3?|\.db-wal|\.db-shm|\.log|\.py|\.toml|\.env.*)$|^FIXTURE_DATA$")
TEXT_SUFFIXES = {".html", ".js", ".css", ".txt", ".xml", ".svg", ".webmanifest"}
# A bare "http://localhost" is React Router's placeholder base for parsing paths, not a network target. Real requests
# are covered by the browser tests, which fail on any request leaving the site's own origin.
LOCAL_ADDRESSES = re.compile(r"localhost:\d+|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|:8000\b")
LOCAL_ADDRESS_ALLOWED = ("data/",)  # snapshot files are scanned by the snapshot validator


class _Head(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.meta: dict[str, str] = {}
        self.links: dict[str, str] = {}
        self.refs: list[str] = []
        self.inline_scripts = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "link":
            self.links[a.get("rel", "")] = a.get("href", "")
            self.refs.append(a.get("href", ""))
        elif tag == "script":
            if a.get("src"):
                self.refs.append(a["src"])
            elif a.get("type") != "application/ld+json":
                self.inline_scripts += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or "") + data


def _page_path(dist: Path, file: Path) -> str:
    rel = file.relative_to(dist).as_posix()
    if rel == "index.html":
        return "/"
    return "/" + rel.removeprefix("_pages/").removesuffix(".html")


def check_site(
    dist: Path, *, site_url: str, netlify_toml: Path | None = None, for_publish: bool = False
) -> Report:
    dist, site_url, report = Path(dist), site_url.rstrip("/"), Report()
    err = report.errors.append
    for name in REQUIRED:
        if not (dist / name).exists():
            err(f"missing {name}")
    if report.errors:
        return report

    snapshot = validate_snapshot(dist / "data" / "v1", for_publish=for_publish)
    report.errors += [f"data/v1: {e}" for e in snapshot.errors]
    report.warnings += [f"data/v1: {w}" for w in snapshot.warnings]
    report.manifest = snapshot.manifest
    indexable = bool(snapshot.manifest) and snapshot.manifest.get("origin") == "production"

    for file in sorted(p for p in dist.rglob("*") if p.is_file()):
        rel = file.relative_to(dist).as_posix()
        if FORBIDDEN_NAMES.search(file.name):
            err(f"{rel} must not be published")
        if file.suffix in TEXT_SUFFIXES and not rel.startswith(LOCAL_ADDRESS_ALLOWED):
            m = LOCAL_ADDRESSES.search(file.read_text(encoding="utf-8", errors="replace"))
            if m:
                err(f"{rel} refers to a local address ({m.group(0)}); the site must not depend on a private backend")

    pages = [dist / "index.html", dist / "404.html", *sorted((dist / "_pages").rglob("*.html"))]
    canonicals: dict[str, bool] = {}
    for file in pages:
        rel, head = file.relative_to(dist).as_posix(), _Head()
        head.feed(file.read_text(encoding="utf-8"))
        if not (head.title or "").strip() or head.title.strip().lower() == "frontend":
            err(f"{rel}: missing or placeholder <title>")
        if len(head.meta.get("description", "")) < 20:
            err(f"{rel}: missing meta description")
        if head.inline_scripts:
            err(f"{rel}: has an inline script, which the Content-Security-Policy blocks")
        for ref in head.refs:
            if ref.startswith("/") and not ref.startswith("//") and not (dist / ref.lstrip("/").split("?")[0]).exists():
                err(f"{rel}: references {ref}, which is not in the build")
        if file.name != "404.html":
            expected = f"{site_url}{_page_path(dist, file)}"
            if head.links.get("canonical") != expected:
                err(f"{rel}: canonical is {head.links.get('canonical')!r}, expected {expected!r}")
            if head.meta.get("og:url") != expected:
                err(f"{rel}: og:url is {head.meta.get('og:url')!r}, expected {expected!r}")
            if head.meta.get("og:image", "") != f"{site_url}/og-card.png":
                err(f"{rel}: og:image must be the absolute site card")
            canonicals[expected] = "robots" not in head.meta
        if for_publish and "robots" in head.meta and "noindex" in head.meta["robots"] and "/health" not in rel and rel != "404.html":
            err(f"{rel}: is marked noindex in a publishable build")

    robots = (dist / "robots.txt").read_text(encoding="utf-8")
    if indexable:
        sitemap = dist / "sitemap.xml"
        if not sitemap.exists():
            err("missing sitemap.xml")
        else:
            listed = set(re.findall(r"<loc>([^<]+)</loc>", sitemap.read_text(encoding="utf-8")))
            for url, is_indexable in canonicals.items():
                if is_indexable and url not in listed:
                    err(f"sitemap.xml does not list {url}")
            for url in listed - set(canonicals):
                err(f"sitemap.xml lists {url}, which has no page")
        if f"Sitemap: {site_url}/sitemap.xml" not in robots:
            err("robots.txt does not point at the sitemap")
    elif "Disallow: /" not in robots:
        err("a non-production build must forbid crawling in robots.txt")

    if netlify_toml is not None:
        _check_netlify(netlify_toml, report)
    return report


def _check_netlify(path: Path, report: Report) -> None:
    err = report.errors.append
    try:
        cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        err(f"netlify.toml cannot be read: {exc}")
        return
    redirects = cfg.get("redirects", [])
    first_data = next((i for i, r in enumerate(redirects) if r["from"] == "/data/*"), None)
    if first_data is None or redirects[first_data].get("status") != 404:
        err("netlify.toml: /data/* must answer a missing file with status 404")
    spa = [i for i, r in enumerate(redirects) if r.get("status") == 200 and r["from"].endswith("*")]
    if first_data is not None and any(i < first_data for i in spa):
        err("netlify.toml: a wildcard rewrite precedes the /data/* rule and would swallow missing data files")
    if any(r["from"] == "/*" and r.get("status") == 200 for r in redirects):
        err("netlify.toml: a catch-all /* rewrite makes every unknown address a 200 page; list the routes instead")
    values = next((h["values"] for h in cfg.get("headers", []) if h["for"] == "/*"), {})
    csp = values.get("Content-Security-Policy", "")
    for needle in ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'"):
        if needle not in csp:
            err(f"netlify.toml: Content-Security-Policy lacks {needle}")
    if re.search(r"script-src[^;]*'unsafe-(inline|eval)'", csp):
        err("netlify.toml: script-src must not allow unsafe-inline or unsafe-eval")
    for header in ("X-Content-Type-Options", "Referrer-Policy", "Strict-Transport-Security"):
        if header not in values:
            err(f"netlify.toml: {header} is not set")

import shutil
from pathlib import Path

import pytest

from nzstats.publish.sitecheck import check_site

SITE = "https://nzstats.example"
ROOT = Path(__file__).resolve().parents[3]
PAGE = """<!doctype html><html lang="en"><head><meta charset="UTF-8" /><title>{title}</title>
<meta name="description" content="A description that is long enough to be useful." />
<link rel="canonical" href="{url}" /><meta property="og:url" content="{url}" />
<meta property="og:image" content="{site}/og-card.png" />{extra}
<script type="module" src="/assets/app.js"></script></head><body><div id="root"></div></body></html>"""


def page(path: str, extra: str = "") -> str:
    url = f"{SITE}{path}"
    return PAGE.format(title=f"Page {path}", url=url, site=SITE, extra=extra)


@pytest.fixture()
def site(snapshot, tmp_path) -> Path:
    """A minimal built site around a snapshot: just what the checker looks at."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "_pages" / "stories").mkdir(parents=True)
    (dist / "assets" / "app.js").write_text("console.log('app')")
    (dist / "index.html").write_text(page("/"))
    (dist / "404.html").write_text(page("/404"))
    (dist / "_pages" / "stories.html").write_text(page("/stories"))
    (dist / "_pages" / "stories" / "a-2026-06.html").write_text(page("/stories/a-2026-06"))
    (dist / "favicon.svg").write_text("<svg/>")
    (dist / "og-card.png").write_bytes(b"\x89PNG")
    (dist / "data-not-found.json").write_text("{}")
    (dist / "_redirects").write_text("/stories /_pages/stories.html 200\n")
    (dist / "robots.txt").write_text(
        "User-agent: *\nDisallow: /\n"
    )  # fixture snapshot: not indexable
    shutil.copytree(snapshot, dist / "data" / "v1")
    return dist


def run(dist: Path, **kw):
    return check_site(dist, site_url=SITE, netlify_toml=ROOT / "netlify.toml", **kw)


def errors(dist: Path, **kw) -> str:
    return "\n".join(run(dist, **kw).errors)


def test_a_complete_site_passes_and_the_real_netlify_config_is_acceptable(site):
    assert run(site).ok, run(site).errors


def test_a_fixture_site_can_not_be_checked_for_publication(site):
    assert "only production data" in errors(site, for_publish=True)


def test_missing_required_files_are_reported(site):
    (site / "404.html").unlink()
    assert "missing 404.html" in errors(site)


def test_placeholder_title_and_wrong_canonical_are_reported(site):
    (site / "_pages" / "stories.html").write_text(
        page("/stories").replace("Page /stories", "frontend")
    )
    (site / "_pages" / "stories" / "a-2026-06.html").write_text(page("/stories/other"))
    out = errors(site)
    assert "placeholder <title>" in out and "canonical is" in out


def test_inline_scripts_are_reported_because_the_policy_blocks_them(site):
    (site / "index.html").write_text(page("/", "<script>alert(1)</script>"))
    assert "inline script" in errors(site)


def test_json_ld_is_not_an_inline_script(site):
    (site / "index.html").write_text(page("/", '<script type="application/ld+json">{}</script>'))
    assert run(site).ok


def test_a_reference_to_a_missing_asset_is_reported(site):
    (site / "assets" / "app.js").unlink()
    assert "references /assets/app.js" in errors(site)


def test_local_addresses_and_secrets_files_are_reported(site):
    (site / "assets" / "app.js").write_text("fetch('http://127.0.0.1:8000/api/cpi')")
    (site / "assets" / "app.js.map").write_text("{}")
    (site / "data" / "v1" / "nzstats.db").write_text("x")
    out = errors(site)
    assert (
        "local address" in out and "app.js.map must not be published" in out and "nzstats.db" in out
    )


def test_react_routers_bare_localhost_placeholder_is_not_a_backend(site):
    (site / "assets" / "app.js").write_text("let r=`http://localhost`;")
    assert run(site).ok


def test_a_snapshot_inside_the_site_is_validated_too(site):
    path = site / "data" / "v1" / "cpi.json"
    path.write_text(path.read_text().replace("2026", "2025", 1))
    assert "data/v1:" in errors(site) and "manifest hash" in errors(site)


def _toml(tmp_path, body: str) -> Path:
    path = tmp_path / "netlify.toml"
    path.write_text(body)
    return path


GOOD = """
[[redirects]]
  from = "/data/*"
  to = "/data-not-found.json"
  status = 404
[[redirects]]
  from = "/stories/*"
  to = "/index.html"
  status = 200
[[headers]]
  for = "/*"
  [headers.values]
    Content-Security-Policy = "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'"
    X-Content-Type-Options = "nosniff"
    Referrer-Policy = "no-referrer"
    Strict-Transport-Security = "max-age=1"
"""


@pytest.mark.parametrize(
    ("body", "complaint"),
    [
        (GOOD.replace("status = 404", "status = 200"), "/data/* must answer"),
        (
            GOOD + '[[redirects]]\n  from = "/*"\n  to = "/index.html"\n  status = 200\n',
            "catch-all",
        ),
        (GOOD.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'"), "unsafe-inline"),
        (GOOD.replace("frame-ancestors 'none'", ""), "frame-ancestors"),
        (GOOD.replace("X-Content-Type-Options", "X-Other"), "X-Content-Type-Options"),
        (
            GOOD.split("[[redirects]]", 2)[0]
            + '[[redirects]]\n  from = "/stories/*"\n  to = "/index.html"\n  status = 200\n'
            + "[[redirects]]"
            + GOOD.split("[[redirects]]", 2)[1]
            + "[[headers]]"
            + GOOD.split("[[headers]]")[1],
            "precedes the /data/* rule",
        ),
    ],
)
def test_netlify_toml_mistakes_are_reported(site, tmp_path, body, complaint):
    report = check_site(site, site_url=SITE, netlify_toml=_toml(tmp_path, body))
    assert complaint in "\n".join(report.errors)


def test_the_known_good_config_passes(site, tmp_path):
    assert check_site(site, site_url=SITE, netlify_toml=_toml(tmp_path, GOOD)).ok


@pytest.fixture()
def production_site(production_dir, tmp_path, site) -> Path:
    """The same minimal site around a production-origin snapshot, with the SEO files a published build has."""
    from nzstats.publish.snapshot import export_snapshot
    from tests.publish.conftest import EXPORT_NOW

    export_snapshot(production_dir, tmp_path / "prod-snapshot", now=EXPORT_NOW)
    shutil.rmtree(site / "data" / "v1")
    shutil.copytree(tmp_path / "prod-snapshot", site / "data" / "v1")
    (site / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
    urls = "".join(
        f"<url><loc>{SITE}{p}</loc></url>" for p in ("/", "/stories", "/stories/a-2026-06")
    )
    (site / "sitemap.xml").write_text(f"<urlset>{urls}</urlset>")
    return site


def test_a_production_site_with_a_complete_sitemap_is_publishable(production_site):
    report = run(production_site, for_publish=True)
    assert report.ok, report.errors


def test_the_sitemap_must_list_every_indexable_page_and_nothing_else(production_site):
    (production_site / "sitemap.xml").write_text(
        f"<urlset><url><loc>{SITE}/</loc></url><url><loc>{SITE}/ghost</loc></url></urlset>"
    )
    out = errors(production_site, for_publish=True)
    assert "does not list " + SITE + "/stories" in out and "lists " + SITE + "/ghost" in out


def test_robots_must_point_at_the_sitemap_and_a_published_page_must_not_be_noindex(production_site):
    (production_site / "robots.txt").write_text("User-agent: *\nAllow: /\n")
    (production_site / "_pages" / "stories.html").write_text(
        page("/stories", '<meta name="robots" content="noindex" />')
    )
    out = errors(production_site, for_publish=True)
    assert "does not point at the sitemap" in out and "marked noindex" in out

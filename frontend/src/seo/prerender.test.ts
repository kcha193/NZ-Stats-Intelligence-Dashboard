import { describe, expect, it } from "vitest";
import type { CpiDashboard, EctDashboard, Overview, SeriesData } from "@/api/types";
import cpi from "@/test/fixtures/cpi.json";
import ect from "@/test/fixtures/ect.json";
import overview from "@/test/fixtures/overview.json";
import arrivals from "@/test/fixtures/series_arrivals_ry.json";
import departures from "@/test/fixtures/series_departures_ry.json";
import net from "@/test/fixtures/series_net_ry.json";
import nonNz from "@/test/fixtures/series_net_nonnz_ry.json";
import nz from "@/test/fixtures/series_net_nz_ry.json";
import { appShell, buildPages, redirectsFile, renderHtml, robotsTxt, sitemapXml, type PageSpec, type Template } from "./prerender";
import { ROUTE_META } from "./routes";

const SITE = "https://nzstats.example";
const sources = {
  cpi: cpi as CpiDashboard, ect: ect as EctDashboard, overview: overview as Overview,
  net: net as SeriesData, arrivals: arrivals as SeriesData, departures: departures as SeriesData,
  nz: nz as SeriesData, nonNz: nonNz as SeriesData,
};
const meta = { origin: "production" as const, dataUpdatedAt: "2026-10-22T20:04:11+13:00" };
const template: Template = `<!doctype html><html lang="en"><head><meta charset="UTF-8" /><title>frontend</title>
<meta name="description" content="x" /></head><body><div id="root"></div></body></html>`;

describe("buildPages", () => {
  const pages = buildPages(sources, meta);

  it("covers every public route and every current story, each with its own title and description", () => {
    const paths = pages.map((p) => p.path);
    for (const route of Object.keys(ROUTE_META)) expect(paths).toContain(route);
    expect(paths.filter((p) => p.startsWith("/stories/")).length).toBeGreaterThanOrEqual(8);
    expect(new Set(pages.map((p) => p.title)).size).toBe(pages.length);
    for (const p of pages) {
      expect(p.description.length).toBeGreaterThan(40);
      expect(p.description.length).toBeLessThanOrEqual(200);
    }
  });

  it("describes a story with its headline, deck, release date and source", () => {
    const story = pages.find((p) => p.path === "/stories/spending-retail-2026-09" || p.path.startsWith("/stories/spending-retail"))!;
    expect(story.title).toMatch(/Retail card spending/);
    expect(story.kind).toBe("article");
    expect(story.published).toMatch(/^2026-/);
    expect(story.noscript).toContain("Stats NZ");
    expect(story.noscript).toContain(story.title);
  });

  it("keeps the data-health page out of the index", () => {
    expect(pages.find((p) => p.path === "/health")!.indexable).toBe(false);
  });
});

describe("renderHtml", () => {
  const page = buildPages(sources, meta).find((p) => p.path.startsWith("/stories/inflation"))!;
  const html = renderHtml(template, page, { siteUrl: SITE, indexable: true });

  it("sets title, description, canonical and social tags from the page", () => {
    expect(html).toContain(`<title>${page.title} | NZ Stats Intelligence</title>`.replace(/&/g, "&amp;"));
    expect(html).toContain(`rel="canonical" href="${SITE}${page.path}"`);
    expect(html).toContain('property="og:type" content="article"');
    expect(html).toContain(`property="og:url" content="${SITE}${page.path}"`);
    expect(html).toContain(`property="og:image" content="${SITE}/og-card.png"`);
    expect(html).toContain('name="twitter:card" content="summary_large_image"');
    expect(html).not.toContain("<title>frontend</title>");
    expect(html.match(/name="description"/g)).toHaveLength(1);
  });

  it("describes the story to crawlers as an article that is based on the Stats NZ release", () => {
    const ld = /<script type="application\/ld\+json">(.*?)<\/script>/s.exec(html)![1];
    const data = JSON.parse(ld.replace(/\\u003c/g, "<"));
    expect(data["@type"]).toBe("Article");
    expect(data.headline).toBe(page.title);
    expect(data.isBasedOn).toMatch(/^https:\/\/www\.stats\.govt\.nz\//);
  });

  it("puts a readable summary in noscript, leaving the app root untouched", () => {
    expect(html).toContain("<noscript>");
    expect(html).toContain('<div id="root"></div>');
  });

  it("escapes upstream text everywhere it is placed", () => {
    const evil = { ...page, title: 'A "quoted" <b>title</b> & more', description: '</script><script>alert(1)</script>' };
    const out = renderHtml(template, evil, { siteUrl: SITE, indexable: true });
    expect(out).not.toContain("<script>alert(1)");
    expect(out).not.toContain("<b>title</b>");
    expect(out).toContain("&lt;b&gt;title&lt;/b&gt;");
  });

  it("marks a non-indexable build noindex", () => {
    expect(renderHtml(template, page, { siteUrl: SITE, indexable: false })).toContain('name="robots" content="noindex,nofollow"');
    expect(html).not.toContain('name="robots"');
  });
});

describe("site files", () => {
  const pages = buildPages(sources, meta);

  it("lists indexable pages only, with absolute URLs and a last-modified date", () => {
    const xml = sitemapXml(pages, SITE, "2026-10-22");
    expect(xml).toContain(`<loc>${SITE}/</loc>`);
    expect(xml).toContain(`<loc>${SITE}/stories</loc>`);
    expect(xml).not.toContain("/health");
    expect(xml).toContain("<lastmod>2026-10-22</lastmod>");
    expect(xml.match(/<loc>/g)!.length).toBe(pages.filter((p) => p.indexable).length);
  });

  it("allows crawling and points at the sitemap, or forbids everything for a fixture build", () => {
    expect(robotsTxt(SITE, true)).toMatch(/Allow: \/\n[\s\S]*Sitemap: https:\/\/nzstats\.example\/sitemap\.xml/);
    expect(robotsTxt(SITE, false)).toContain("Disallow: /");
    expect(robotsTxt(SITE, false)).not.toContain("Sitemap");
  });

  it("rewrites each prerendered address to its own file, with the dashboard routes and stories first", () => {
    const rules = redirectsFile(pages);
    expect(rules).toContain("/stories/inflation-annual-2026-06 /_pages/stories/inflation-annual-2026-06.html 200");
    expect(rules).toContain("/inflation /_pages/inflation.html 200");
    expect(rules).not.toMatch(/^\/ /m);
  });
});


describe("hardening", () => {
  const page = buildPages(sources, meta).find((p) => p.path.startsWith("/stories/inflation"))!;

  it("treats replacement patterns in upstream text literally", () => {
    const tricky: PageSpec = { ...page, title: "Costs $& $' $` $$ $1", description: "Prices rose $$ and $& fell" };
    const out = renderHtml(template, tricky, { siteUrl: SITE, indexable: true });
    expect(out).toContain("<title>Costs $&amp; $&#39; $` $$ $1 | NZ Stats Intelligence</title>");
    expect(out).toContain('content="Prices rose $$ and $&amp; fell"');
    expect(out.match(/<\/head>/g)).toHaveLength(1);
    expect(out.match(/<title>/g)).toHaveLength(1);
  });

  it("refuses a page path that could inject a rewrite rule or leave the output directory", () => {
    for (const path of ["/stories/a b", "/stories/../../x", "/stories/x\n/evil /y 200", "/Stories/X"]) {
      expect(() => redirectsFile([{ ...page, path }])).toThrow(/page path/);
      expect(() => renderHtml(template, { ...page, path }, { siteUrl: SITE, indexable: true })).toThrow(/page path/);
    }
  });

  it("refuses a site URL that is not a plain https origin", () => {
    for (const bad of ["http://nzstats.example", 'https://x.example"><script>', "https://x.example/path", "javascript:alert(1)"]) {
      expect(() => renderHtml(template, page, { siteUrl: bad, indexable: true })).toThrow(/site URL/);
    }
  });

  it("only links to Stats NZ as the source in structured data", () => {
    const html = renderHtml(template, { ...page, sourceUrl: "https://evil.example/x" }, { siteUrl: SITE, indexable: true });
    expect(html).not.toContain("evil.example");
  });

  it("serves unknown and dynamic addresses from a neutral, unindexed shell with no canonical", () => {
    const html = renderHtml(template, appShell(), { siteUrl: SITE, indexable: true });
    expect(html).toContain('name="robots" content="noindex,follow"');
    expect(html).not.toContain('rel="canonical"');
    expect(html).not.toContain('property="og:url"');
    expect(html).toContain("<noscript>");
  });
});

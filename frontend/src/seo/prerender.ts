import { escapeHtml } from "@/lib/format";
import { composeStories, type StorySources } from "@/stories/compose";
import { CATEGORY_LABEL, type Story } from "@/stories/types";
import { ROUTE_META, SITE_NAME, withSiteName } from "./routes";

/**
 * Build-time page metadata for the published site. The app itself is rendered in the browser; these pages add what
 * crawlers that do not run JavaScript need: the title, description, canonical address, social tags and a plain-text
 * summary. They are generated from the same snapshot and the same story builders as the app, so they cannot disagree.
 */

export type Template = string;
export type SnapshotMeta = { origin: "production" | "fixture"; dataUpdatedAt: string | null };

export type PageSpec = {
  path: string;
  title: string;
  description: string;
  kind: "website" | "article";
  indexable: boolean;
  /** HTML, already escaped. Shown only when scripts are off. */
  noscript: string;
  published?: string;
  modified?: string;
  sourceUrl?: string | null;
};

const OG_IMAGE = "/og-card.png";
const MAX_DESCRIPTION = 200;
const NOT_INDEXED = new Set(["/health"]);

const clip = (text: string, max = MAX_DESCRIPTION): string => {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  const cut = flat.slice(0, max - 1);
  return `${cut.slice(0, cut.lastIndexOf(" "))}…`;
};

const sourceLine = (s: Story): string =>
  `Source: Stats NZ, ${escapeHtml(s.provenance.title)}${s.dataStatus === "provisional" ? " (provisional)" : ""}. Licensed CC BY 4.0.`;

function storyIndex(stories: Story[]): string {
  if (stories.length === 0) return "";
  const items = stories
    .map((s) => `<li><a href="/stories/${escapeHtml(s.id)}">${escapeHtml(s.headline)}</a></li>`)
    .join("");
  return `<h2>Stories</h2><ul>${items}</ul>`;
}

function routePage(path: string, stories: Story[], modified: string | undefined): PageSpec {
  const m = ROUTE_META[path];
  const index = path === "/" || path === "/stories" ? storyIndex(stories) : "";
  return {
    path,
    title: m.title,
    description: m.description,
    kind: "website",
    indexable: !NOT_INDEXED.has(path),
    modified,
    noscript:
      `<h1>${escapeHtml(m.title)}</h1><p>${escapeHtml(m.description)}</p>${index}` +
      `<p>This site needs JavaScript to draw its charts. Data: Stats NZ, licensed CC BY 4.0.</p>`,
  };
}

function storyPage(s: Story, modified: string | undefined): PageSpec {
  return {
    path: `/stories/${s.id}`,
    title: s.headline,
    description: clip(s.dek),
    kind: "article",
    indexable: true,
    published: s.provenance.publishedAt,
    modified,
    sourceUrl: s.provenance.pageUrl,
    noscript:
      `<h1>${escapeHtml(s.headline)}</h1><p>${escapeHtml(s.dek)}</p>` +
      `<p><strong>${escapeHtml(s.stat.value)}</strong> ${escapeHtml(s.stat.unit)}</p>` +
      `<p>${escapeHtml(CATEGORY_LABEL[s.category])}. ${sourceLine(s)}</p>` +
      `<p>This site needs JavaScript to draw its charts.</p>`,
  };
}

export function buildPages(sources: StorySources, meta: SnapshotMeta): PageSpec[] {
  const stories = composeStories(sources);
  const modified = meta.dataUpdatedAt ?? undefined;
  return [
    ...Object.keys(ROUTE_META).map((path) => routePage(path, stories, modified)),
    ...stories.map((s) => storyPage(s, modified)),
  ];
}

/** Text placed in JSON-LD must not be able to close the script element. */
const safeJson = (data: unknown): string => JSON.stringify(data).replace(/</g, "\\u003c");

function jsonLd(page: PageSpec, url: string, siteUrl: string): unknown {
  if (page.kind === "article") {
    return {
      "@context": "https://schema.org",
      "@type": "Article",
      headline: page.title,
      description: page.description,
      inLanguage: "en-NZ",
      mainEntityOfPage: url,
      datePublished: page.published,
      dateModified: page.modified,
      isBasedOn: page.sourceUrl ?? undefined,
      publisher: { "@type": "Organization", name: SITE_NAME, url: siteUrl },
    };
  }
  if (page.path === "/") {
    return { "@context": "https://schema.org", "@type": "WebSite", name: SITE_NAME, url: siteUrl, inLanguage: "en-NZ" };
  }
  return undefined;
}

export function renderHtml(template: Template, page: PageSpec, opts: { siteUrl: string; indexable: boolean }): string {
  const { siteUrl } = opts;
  const url = `${siteUrl}${page.path === "/" ? "/" : page.path}`;
  const title = escapeHtml(withSiteName(page.title));
  const description = escapeHtml(page.description);
  const robots = !opts.indexable ? "noindex,nofollow" : page.indexable ? null : "noindex,follow";
  const ld = jsonLd(page, url, siteUrl);
  const head = [
    `<meta name="description" content="${description}" />`,
    robots && `<meta name="robots" content="${robots}" />`,
    `<link rel="canonical" href="${escapeHtml(url)}" />`,
    `<meta property="og:site_name" content="${SITE_NAME}" />`,
    `<meta property="og:locale" content="en_NZ" />`,
    `<meta property="og:type" content="${page.kind}" />`,
    `<meta property="og:title" content="${title}" />`,
    `<meta property="og:description" content="${description}" />`,
    `<meta property="og:url" content="${escapeHtml(url)}" />`,
    `<meta property="og:image" content="${siteUrl}${OG_IMAGE}" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    `<meta property="og:image:alt" content="${SITE_NAME}: New Zealand's economy, explained from official Stats NZ releases" />`,
    page.published && `<meta property="article:published_time" content="${escapeHtml(page.published)}" />`,
    page.modified && page.kind === "article" && `<meta property="article:modified_time" content="${escapeHtml(page.modified)}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${title}" />`,
    `<meta name="twitter:description" content="${description}" />`,
    `<meta name="twitter:image" content="${siteUrl}${OG_IMAGE}" />`,
    ld && `<script type="application/ld+json">${safeJson(ld)}</script>`,
  ]
    .filter(Boolean)
    .join("\n    ");
  return template
    .replace(/<title>[\s\S]*?<\/title>/, `<title>${title}</title>`)
    .replace(/\s*<meta name="description"[^>]*>/, "")
    .replace("</head>", `    ${head}\n  </head>`)
    .replace('<div id="root"></div>', `<div id="root"></div>\n    <noscript>${page.noscript}</noscript>`);
}

const xml = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function sitemapXml(pages: PageSpec[], siteUrl: string, lastmod: string): string {
  const urls = pages
    .filter((p) => p.indexable)
    .map((p) => `  <url><loc>${xml(siteUrl + p.path)}</loc><lastmod>${lastmod}</lastmod></url>`)
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}

export function robotsTxt(siteUrl: string, indexable: boolean): string {
  return indexable
    ? `User-agent: *\nAllow: /\n\nSitemap: ${siteUrl}/sitemap.xml\n`
    : `User-agent: *\nDisallow: /\n`;
}

/** Each prerendered address is served from its own file; the rest of the routing lives in netlify.toml. */
export function redirectsFile(pages: PageSpec[]): string {
  const rules = pages.filter((p) => p.path !== "/").map((p) => `${p.path} /_pages${p.path}.html 200`);
  return `# Generated by the static build. Prerendered pages first; netlify.toml holds the fallbacks.\n${rules.join("\n")}\n`;
}

// Writes the public-site files that depend on the snapshot: per-page HTML metadata, sitemap.xml, robots.txt,
// the prerendered-page rewrites, 404.html and the not-found JSON. Run after `vite build --mode static`.
//
//   node scripts/prerender.mjs --snapshot <dir> --dist dist --site-url https://example.com
//
// It loads the same story builders the app uses (through Vite's SSR loader) so the metadata cannot disagree with the pages.
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseArgs } from "node:util";
import { createServer } from "vite";

const { values } = parseArgs({
  options: {
    snapshot: { type: "string" },
    dist: { type: "string", default: "dist" },
    "site-url": { type: "string", default: process.env.SITE_URL },
  },
});
const fail = (msg) => {
  console.error(`prerender: ${msg}`);
  process.exit(1);
};
if (!values.snapshot) fail("--snapshot <dir> is required");

const siteUrl = (values["site-url"] ?? "").replace(/\/+$/, "");
if (!/^https:\/\/[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::\d{1,5})?$/i.test(siteUrl)) fail("--site-url (or SITE_URL) must be an https origin such as https://example.com");

const read = async (name) => JSON.parse(await readFile(path.join(values.snapshot, name), "utf8"));
const payload = async (name) => (await read(name)).payload;
const manifest = await read("manifest.json");
const indexable = manifest.origin === "production";

const seriesKeys = { net: "mig.ry.net", arrivals: "mig.ry.arrivals", departures: "mig.ry.departures", nz: "mig.ry.net.nz", nonNz: "mig.ry.net.nonnz" };
const sources = { cpi: await payload("cpi.json"), ect: await payload("ect.json"), overview: await payload("overview.json") };
for (const [field, key] of Object.entries(seriesKeys)) sources[field] = await payload(`series/${key}.json`);

const vite = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
try {
  const { appShell, buildPages, renderHtml, sitemapXml, robotsTxt, redirectsFile } = await vite.ssrLoadModule("/src/seo/prerender.ts");
  const pages = buildPages(sources, { origin: manifest.origin, dataUpdatedAt: manifest.data_updated_at });
  const template = await readFile(path.join(values.dist, "index.html"), "utf8");
  const write = async (rel, text) => {
    const file = path.join(values.dist, rel);
    await mkdir(path.dirname(file), { recursive: true });
    await writeFile(file, text);
  };

  for (const page of pages) {
    const html = renderHtml(template, page, { siteUrl, indexable });
    await write(page.path === "/" ? "index.html" : `_pages${page.path}.html`, html);
  }
  // Unknown addresses get a real 404 status; the page is the app shell, which shows its own "not found" message.
  const notFound = { path: "/404", title: "Page not found", description: "That page does not exist on this site.", kind: "website", indexable: false, noscript: "<h1>Page not found</h1>" };
  await write("404.html", renderHtml(template, notFound, { siteUrl, indexable: false }));
  // Dynamic and unknown addresses (/releases/:id, a story period that has moved on) get a shell with no canonical.
  await write("_pages/app-shell.html", renderHtml(template, appShell(), { siteUrl, indexable }));
  await write("data-not-found.json", `${JSON.stringify({ detail: "not found" })}\n`);
  await write("_redirects", redirectsFile(pages));
  await write("robots.txt", robotsTxt(siteUrl, indexable));
  if (indexable) await write("sitemap.xml", sitemapXml(pages, siteUrl, (manifest.data_updated_at ?? manifest.generated_at).slice(0, 10)));
  console.log(`prerender: ${pages.length} pages, origin ${manifest.origin}, indexable ${indexable} -> ${values.dist}`);
} finally {
  await vite.close();
}

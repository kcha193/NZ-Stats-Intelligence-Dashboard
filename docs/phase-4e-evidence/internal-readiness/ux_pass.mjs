// Real-data browser pass over the native app serving the restored production copy (loopback only).
// node ux_pass.mjs <frontend dir> <base url> <out dir>
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const [frontend, base, out] = process.argv.slice(2);
const { chromium } = createRequire(join(frontend, "package.json"))("@playwright/test");
mkdirSync(out, { recursive: true });

const routes = ["/", "/inflation", "/gdp", "/labour-market", "/migration", "/electronic-card-transactions",
  "/economic-outlook", "/calendar", "/health", "/stories", "/ocr", "/no-such-page"];
const viewports = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } };
const exportRoutes = ["/inflation", "/gdp", "/labour-market", "/migration", "/electronic-card-transactions"];

const browser = await chromium.launch();
const results = [];
for (const [vpName, viewport] of Object.entries(viewports)) {
  for (const scheme of ["light", "dark"]) {
    const ctx = await browser.newContext({ viewport, colorScheme: scheme, acceptDownloads: true });
    for (const route of routes) {
      const page = await ctx.newPage();
      const pageErrors = [], consoleErrors = [], external = [], failed = [];
      page.on("pageerror", (e) => pageErrors.push(e.message));
      page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
      page.on("request", (r) => { if (!r.url().startsWith(base) && !r.url().startsWith("data:") && !r.url().startsWith("blob:")) external.push(r.url()); });
      page.on("response", (r) => { if (r.status() >= 400 && r.url().includes("/api/")) failed.push(`${r.status()} ${r.url()}`); });
      const t0 = Date.now();
      await page.goto(base + route, { waitUntil: "networkidle" });
      const h1 = await page.locator("h1").first().textContent({ timeout: 10000 }).catch(() => null);
      const loadMs = Date.now() - t0;
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      const body = await page.locator("body").innerText();
      const r = {
        viewport: vpName, scheme, route, h1, loadMs, overflow,
        canvases: await page.locator("canvas").count(),
        freshness: /Data last updated|last checked|Captured|captured/i.test(body),
        statsNzAttribution: /Stats NZ|stats\.govt\.nz/i.test(body),
        loadingStuck: /^\s*Loading/m.test(body),
        darkClass: await page.evaluate(() => document.documentElement.classList.contains("dark")),
        pageErrors, consoleErrors, external, failedApi: failed,
      };
      if (scheme === "light" && vpName === "desktop" || route === "/gdp" || route === "/labour-market") {
        await page.screenshot({ path: join(out, `${vpName}-${scheme}${route.replaceAll("/", "_") || "_home"}.png`), fullPage: false });
      }
      results.push(r);
      await page.close();
    }
    await ctx.close();
  }
}

// Exports: every CSV and PNG button on the data pages, desktop light.
const exports = [];
const ctx = await browser.newContext({ viewport: viewports.desktop, acceptDownloads: true });
for (const route of exportRoutes) {
  const page = await ctx.newPage();
  await page.goto(base + route, { waitUntil: "networkidle" });
  for (const [kind, name] of [["csv", /Download data \(CSV\)/], ["png", /Export image \(PNG\)/]]) {
    const buttons = page.getByRole("button", { name });
    const n = await buttons.count();
    for (let i = 0; i < n; i++) {
      const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 15000 }), buttons.nth(i).click()]);
      const path = join(out, "exports", `${route.slice(1)}-${i}-${dl.suggestedFilename()}`);
      await dl.saveAs(path);
      const buf = readFileSync(path);
      const e = { route, kind, file: dl.suggestedFilename(), bytes: buf.length };
      if (kind === "csv") {
        const text = buf.toString("utf8");
        e.rows = text.trim().split(/\r?\n/).length;
        e.mentionsSource = /stats\.govt\.nz|Stats NZ/i.test(text);
        e.formulaInjectionSafe = !/^[=+\-@]/m.test(text.split(/\r?\n/).map((l) => l.split(",")[0]).join("\n").replace(/^-?\d/mg, ""));
      } else {
        e.pngSignature = buf.subarray(0, 8).toString("hex") === "89504e470d0a1a0a";
        e.width = buf.readUInt32BE(16); e.height = buf.readUInt32BE(20);
      }
      exports.push(e);
    }
  }
  await page.close();
}
await browser.close();
writeFileSync(join(out, "ux-results.json"), JSON.stringify({ base, results, exports }, null, 2));
const bad = results.filter((r) => r.pageErrors.length || r.consoleErrors.length || r.external.length || r.failedApi.length || r.overflow > 1);
console.log(JSON.stringify({
  views: results.length, problemViews: bad.map((r) => ({ v: r.viewport, s: r.scheme, route: r.route, overflow: r.overflow, pe: r.pageErrors, ce: r.consoleErrors, ext: r.external, api: r.failedApi })),
  maxLoadMs: Math.max(...results.map((r) => r.loadMs)), medianLoadMs: results.map((r) => r.loadMs).sort((a, b) => a - b)[results.length >> 1],
  darkModeApplied: results.filter((r) => r.scheme === "dark").every((r) => r.darkClass),
  noStuckLoading: results.every((r) => !r.loadingStuck),
  exports: exports.length, csv: exports.filter((e) => e.kind === "csv").length, png: exports.filter((e) => e.kind === "png").length,
  csvAllSourced: exports.filter((e) => e.kind === "csv").every((e) => e.mentionsSource),
  pngAllValid: exports.filter((e) => e.kind === "png").every((e) => e.pngSignature && e.width > 0),
}, null, 2));

// Browser pass over the Data health page served by the native app (loopback only).
// node ops_ui_pass.mjs <frontend dir> <base url> <out dir>   -> JSON on stdout
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const [frontend, base, out] = process.argv.slice(2);
const { chromium } = createRequire(join(frontend, "package.json"))("@playwright/test");
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const results = [];
for (const [vp, viewport] of Object.entries({ desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } })) {
  for (const scheme of ["light", "dark"]) {
    const ctx = await browser.newContext({ viewport, colorScheme: scheme });
    const page = await ctx.newPage();
    const pageErrors = [], external = [], failed = [];
    page.on("pageerror", (e) => pageErrors.push(e.message));
    page.on("request", (r) => { if (!r.url().startsWith(base) && !r.url().startsWith("data:")) external.push(r.url()); });
    page.on("response", (r) => { if (r.status() >= 400) failed.push(`${r.status()} ${new URL(r.url()).pathname}`); });
    await page.goto(base + "/health", { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "Operations" }).waitFor({ timeout: 10000 });
    const banner = (await page.locator("[data-level]").first().innerText()).replace(/\s+/g, " ");
    const level = await page.locator("[data-level]").first().getAttribute("data-level");
    const text = await page.locator("body").innerText();
    results.push({
      viewport: vp, scheme, banner, level,
      answers: ["Data collection", "Application", "Next official release", "Release calendar", "Latest ingestion", "Backup", "Is each release current?"].filter((t) => text.includes(t)),
      overflow: await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
      pageErrors, external, failed,
    });
    if (scheme === "light") await page.screenshot({ path: join(out, `data-health-${vp}.png`), fullPage: true });
    await ctx.close();
  }
}
await browser.close();
console.log(JSON.stringify(results, null, 2));

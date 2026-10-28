import { expect, test, type Page } from "@playwright/test";
import fixture from "../src/test/fixtures/cpi.json" with { type: "json" };
import { dataUrl, rewrap, STATIC } from "./mode";

// Approved Phase 4 evaluation pattern: retain schema/domain labels and replace observations.
const synthetic = structuredClone(fixture);
for (const [s, series] of synthetic.series.entries()) {
  for (const [i, point] of series.points.entries()) {
    point.index = 1000 + i * 2 + s;
    point.annual_pct = +(1 + (i % 9) * 0.3 + s * 0.01).toFixed(2);
    point.quarterly_pct = +(0.2 + (i % 5) * 0.1 + s * 0.01).toFixed(2);
  }
}
for (const metric of synthetic.analysis.headline_metrics) metric.value = 1.234567;
for (const block of synthetic.contributions) {
  for (const [i, item] of block.items.entries()) item.points = 0.1234567 + i * 0.01;
  block.note = "Synthetic evaluation values, not official statistics.";
}
for (const measure of synthetic.underlying) for (const point of measure.points) point.value = 0.6;
synthetic.analysis.executive_summary = [];
synthetic.analysis.context = [];
synthetic.analysis.release.title = "SYNTHETIC CPI evaluation: June 2026 quarter";
const cpiPath = dataUrl({ path: "cpi", file: "cpi.json" });

async function denyExternal(page: Page) {
  const external: string[] = [];
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") {
      external.push(url.origin);
      return route.abort();
    }
    return route.continue();
  });
  return external;
}

for (const colorScheme of ["light", "dark"] as const) {
  test.describe(`CPI UX ${colorScheme}`, () => {
    test.use({ colorScheme, reducedMotion: "reduce" });

    test("selected range, display precision, CSV and mobile targets", async ({ page }, info) => {
      const external = await denyExternal(page);
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route(`**${cpiPath}`, async (route) => {
        const raw = STATIC ? await (await route.fetch()).json() : null;
        await route.fulfill({ json: rewrap(raw, synthetic) });
      });
      await page.goto("/inflation");
      await expect(page.getByRole("region", { name: "CPI key indicators" })).toBeVisible();
      const targets = await page.locator("fieldset label, button, select, summary").evaluateAll((elements) => elements
        .filter((e) => (e.closest("figure") && (e.tagName === "BUTTON" || e.tagName === "SUMMARY")) || e.matches("fieldset label, select"))
        .map((e) => {
          const r = e.getBoundingClientRect();
          return { label: e.tagName === "SELECT" ? "CPI component" : e.textContent?.trim(), x: r.x, y: r.y, width: r.width, height: r.height };
        }));
      await info.attach("hit-regions", { body: JSON.stringify(targets, null, 2), contentType: "application/json" });
      if (page.viewportSize()!.width < 640) {
        for (const target of targets) {
          expect(target.height, target.label).toBeGreaterThanOrEqual(44);
          expect(target.width, target.label).toBeGreaterThanOrEqual(44);
        }
      }
      for (const [i, a] of targets.entries()) for (const b of targets.slice(i + 1)) {
        const overlap = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x) > 0.5
          && Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y) > 0.5;
        expect(overlap, `${a.label} overlaps ${b.label}`).toBe(false);
      }
      const ranges = page.getByRole("group", { name: "History range" });
      const firstRadio = ranges.getByRole("radio").first();
      await firstRadio.focus();
      await page.keyboard.press("ArrowRight");
      await expect(ranges.getByRole("radio", { name: "5 years", exact: true })).toBeChecked();
      // Native radio focus is displayed on its peer span, including in reduced motion.
      expect(await ranges.locator("input:checked + span").evaluate((e) => getComputedStyle(e).outlineStyle)).toBe("solid");
      const disclosure = page.locator("summary").filter({ hasText: "View data table" }).first();
      await disclosure.focus();
      await page.keyboard.press("Enter");
      const table = page.getByRole("table").first();
      for (const [name, count] of [["Full history", 58], ["3 years", 12], ["5 years", 20], ["10 years", 40]] as const) {
        await ranges.getByText(name, { exact: true }).click();
        await expect(table.getByRole("row")).toHaveCount(count + 1);
        await expect(table.locator("caption")).toContainText(`Showing all ${count} periods (${count} rows)`);
        await expect(table.getByRole("row").last()).toContainText("Jun 2026");
      }
      await ranges.getByText("Full history", { exact: true }).click();
      await expect(table.getByRole("columnheader", { name: "Annual change (%)", exact: true })).toBeVisible();
      await table.locator("caption").scrollIntoViewIfNeeded();
      await page.screenshot({ path: info.outputPath("table-window.png"), scale: "css" });
      const downloadButton = page.getByRole("button", { name: /download data/i }).first();
      const [download] = await Promise.all([page.waitForEvent("download"), downloadButton.click()]);
      const chunks: Buffer[] = [];
      for await (const chunk of (await download.createReadStream())!) chunks.push(Buffer.from(chunk));
      const csv = Buffer.concat(chunks).toString("utf8");
      expect(csv.trim().split("\n")).toHaveLength(59);
      expect(csv).toContain("series_key,series_name,unit,adjustment,source_reference");
      const headline = synthetic.series.find((s) => s.slug === "all_groups" && s.adjustment === "none")!;
      expect(csv).toContain(`${headline.points[0].period},${headline.points[0].index},${headline.points[0].quarterly_pct},${headline.points[0].annual_pct}`);
      const [image] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /export image/i }).first().click()]);
      expect(image.suggestedFilename()).toBe("cpi-annual-inflation.png");
      await expect(page.getByRole("status").filter({ hasText: "Chart image exported" })).toBeVisible();
      const select = page.getByRole("combobox", { name: /CPI component/ });
      await select.focus();
      await page.keyboard.press("ArrowDown");
      await page.keyboard.press("Enter");
      await select.selectOption("housing");
      await page.getByRole("group", { name: "Component view" }).getByText("Index", { exact: true }).click();
      await expect(page.getByRole("heading", { name: /Housing.*index/i })).toBeVisible();

      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
      await page.screenshot({ path: info.outputPath("table-and-controls.png"), fullPage: true, scale: "css" });
      await page.getByRole("heading", { level: 1, name: "Inflation", exact: true }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: info.outputPath("header-and-controls.png"), scale: "css" });
      expect(errors).toEqual([]);
      expect(external).toEqual([]);
    });

    test("one h1 survives loading, server error, pending retry and success", async ({ page }, info) => {
      const external = await denyExternal(page);
      let mode: "loading" | "error" | "retry" | "success" = "loading";
      let release!: () => void;
      let pending = new Promise<void>((resolve) => { release = resolve; });
      await page.route(`**${cpiPath}`, async (route) => {
        if (mode === "loading" || mode === "retry") await pending;
        if (mode === "error") return route.fulfill({ status: 503, json: { detail: "Synthetic service unavailable" } });
        const raw = STATIC ? await (await route.fetch()).json() : null;
        return route.fulfill({ json: rewrap(raw, synthetic) });
      });
      await page.goto("/inflation");
      const h1 = page.getByRole("heading", { level: 1, name: "Inflation", exact: true });
      await expect(h1).toHaveCount(1);
      await expect(page.getByRole("status", { name: "Loading", exact: true })).toBeVisible();
      await page.screenshot({ path: info.outputPath("loading.png") });
      mode = "error";
      release();
      await expect(page.getByRole("alert")).toContainText(/could not be loaded|temporarily unavailable/);
      await expect(h1).toHaveCount(1);
      await page.screenshot({ path: info.outputPath("error.png") });
      mode = "retry";
      pending = new Promise<void>((resolve) => { release = resolve; });
      const retry = page.getByRole("button", { name: "Try again", exact: true });
      await retry.focus();
      await page.keyboard.press("Enter");
      await expect(h1).toHaveCount(1);
      mode = "success";
      release();
      await expect(page.getByRole("region", { name: "CPI key indicators" })).toBeVisible();
      await expect(h1).toHaveCount(1);
      expect(await page.getByRole("heading").evaluateAll((headings) => headings.map((h) => Number(h.tagName[1])).every((level, i, all) => i === 0 || level <= all[i - 1] + 1))).toBe(true);
      expect(external).toEqual([]);
    });

    test("one h1 survives the not-found state", async ({ page }, info) => {
      const external = await denyExternal(page);
      await page.route(`**${cpiPath}`, (route) => route.fulfill({ status: 404, json: { detail: "No synthetic release" } }));
      await page.goto("/inflation");
      await expect(page.getByText(STATIC ? "CPI data has not been published yet" : "CPI data has not been ingested yet", { exact: true })).toBeVisible();
      await expect(page.getByRole("heading", { level: 1, name: "Inflation", exact: true })).toHaveCount(1);
      await page.screenshot({ path: info.outputPath("empty.png") });
      expect(external).toEqual([]);
    });
  });
}

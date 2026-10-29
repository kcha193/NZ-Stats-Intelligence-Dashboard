import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

const routes = ["/", "/gdp", "/labour-market", "/inflation", "/migration", "/electronic-card-transactions", "/economic-outlook", "/ocr"];

for (const colorScheme of ["light", "dark"] as const) {
  test(`Phase 4D populated dashboard smoke: ${colorScheme}`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    for (const route of routes) {
      await page.goto(route);
      await expect(page.locator("h1")).toBeVisible();
      await page.waitForLoadState("networkidle");
      await page.evaluate(() => document.fonts.ready);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
      await page.screenshot({ path: info.outputPath(`${route.slice(1) || "home"}-${colorScheme}.png`), fullPage: true, animations: "disabled" });
    }
    expect(errors).toEqual([]);
  });
}

async function dashboard(page: Page, apiPath: string, file: string) {
  const response = await page.request.get(process.env.E2E_MODE === "static" ? `/data/v1/${file}` : apiPath);
  expect(response.ok()).toBe(true);
  const json = await response.json();
  return process.env.E2E_MODE === "static" ? json.payload : json;
}

test("Phase 4D GDP API, visible values and downloaded stored-vintage CSV agree", async ({ page }) => {
  const data = await dashboard(page, "/api/gdp", "gdp.json");
  const quarter = data.series.find((series: { key: string }) => series.key === "gdp.production.cv.sa.pct_qoq");
  expect(quarter.points.at(-1)).toMatchObject({ period: "2026-06", value: 0.2 });
  await page.goto("/gdp");
  await expect(page.getByRole("region", { name: "GDP key indicators" })).toContainText("0.2%");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: /download data/i }).nth(1).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("gdp-first-published-latest.csv");
  const csv = await readFile((await file.path())!, "utf8");
  expect(csv).toContain("first_basis");
  expect(csv).toContain("earliest stored");
  const march = csv.split(/\r?\n/).find((row) => row.startsWith("2026-03,"))!;
  expect(march).toContain("0.8");
  expect(march).toContain("0.9");
  expect(march).toContain("0.1");
});

test("Phase 4D labour API, separate LCI and downloaded rate CSV agree", async ({ page }) => {
  const data = await dashboard(page, "/api/labour-market", "labour-market.json");
  const series = (key: string) => data.series.find((item: { key: string }) => item.key === key);
  expect(series("hlfs.rate.unemployment.sa").points.at(-1)).toMatchObject({ period: "2026-06", value: 5.6 });
  expect(series("lci.all_wages.pct_yoy")).toMatchObject({ survey: "lci", adjustment: "none" });
  expect(series("lci.all_wages.pct_yoy").points.at(-1).value).toBe(2.0);
  await page.goto("/labour-market");
  await expect(page.getByRole("region", { name: "Labour market key indicators" })).toContainText("5.6%");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: /download data/i }).first().click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("labour-market-rate.csv");
  const csv = await readFile((await file.path())!, "utf8");
  const june = csv.split(/\r?\n/).find((row) => row.startsWith("2026-06,"))!;
  expect(june).toContain("5.6");
  expect(june).toContain("hlfs.rate.unemployment.sa");
});

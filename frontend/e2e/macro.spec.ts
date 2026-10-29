import { expect, test, type Page } from "@playwright/test";

const noOverflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("GDP dashboard: three named measures, revisions, CSV, no overflow, light and dark", async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/gdp");
  await expect(page.getByRole("heading", { level: 1, name: "Gross domestic product" })).toBeVisible();
  const kpis = page.getByRole("region", { name: "GDP key indicators" });
  await expect(kpis).toContainText("0.2%");
  await expect(kpis).toContainText("Annual average GDP growth");
  await expect(page.locator("canvas").first()).toBeVisible();
  await page.screenshot({ path: info.outputPath("gdp-light.png"), fullPage: true });
  await page.getByRole("group", { name: "Growth measure" }).getByText("Annual average", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Annual average GDP growth (production, real)" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /stored baseline and latest/ }).first()).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /download data/i }).nth(1).click()]);
  expect(download.suggestedFilename()).toBe("gdp-first-published-latest.csv");
  expect(await noOverflow(page)).toBeLessThanOrEqual(1);
  await page.emulateMedia({ colorScheme: "dark" });
  await page.reload();
  await expect(page.locator("canvas").first()).toBeVisible();
  await page.screenshot({ path: info.outputPath("gdp-dark.png"), fullPage: true });
  await page.getByRole("link", { name: "Compare with forecasts" }).click();
  await expect(page).toHaveURL(/\/economic-outlook$/);
  expect(errors).toEqual([]);
});

test("Labour market dashboard: HLFS rates and LCI kept apart, revision stated", async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/labour-market");
  await expect(page.getByRole("heading", { level: 1, name: "Labour market" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Labour market key indicators" })).toContainText("5.6%");
  await expect(page.getByText(/earlier stored release showed 5.3%/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Wage rates: Labour Cost Index" })).toBeVisible();
  await page.getByRole("group", { name: "Rate" }).getByText("Underutilisation", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Underutilisation rate (HLFS, seasonally adjusted)" }).first()).toBeVisible();
  await page.screenshot({ path: info.outputPath("labour-light.png"), fullPage: true });
  expect(await noOverflow(page)).toBeLessThanOrEqual(1);
  await page.emulateMedia({ colorScheme: "dark" });
  await page.reload();
  await expect(page.locator("canvas").first()).toBeVisible();
  await page.screenshot({ path: info.outputPath("labour-dark.png"), fullPage: true });
  expect(errors).toEqual([]);
});

test("OCR page shows no figure and says why", async ({ page }, info) => {
  await page.goto("/ocr");
  await expect(page.getByRole("heading", { level: 1, name: "Official Cash Rate" })).toBeVisible();
  await expect(page.getByText(/not yet approved/)).toBeVisible();
  await expect(page.locator("canvas")).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("ocr.png"), fullPage: true });
  expect(await noOverflow(page)).toBeLessThanOrEqual(1);
});

test("navigation reaches the new dashboards", async ({ page }) => {
  await page.goto("/");
  const all = page.getByRole("list", { name: "All pages" });
  for (const name of ["GDP", "Labour market", "Official Cash Rate"]) await expect(all.getByRole("link", { name, exact: true })).toBeVisible();
});

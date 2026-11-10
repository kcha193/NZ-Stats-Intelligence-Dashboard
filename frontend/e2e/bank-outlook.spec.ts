import { expect, test } from "@playwright/test";
import { CONSENSUS, FORECASTS, FRESHNESS, REVISIONS, SUMMARY } from "../src/components/outlook/bank/testData";
import { STATIC } from "./mode";

// SYNTHETIC: fictitious banks and values. The routes below are stubbed; no bank, model or Stats NZ request is made.
const BASE = "**/api/internal/bank-intelligence";

test.beforeEach(async ({ page }) => {
  test.skip(STATIC, "Bank outlooks never appear on the static site.");
  await page.route("**/api/capabilities", (route) => route.fulfill({ json: { research_public: false, internal_drafts: true } }));
  await page.route("**/api/internal/drafts**", (route) => route.fulfill({ status: 404, json: { detail: "not found" } }));
  for (const [name, body] of Object.entries({ summary: SUMMARY, forecasts: FORECASTS, consensus: CONSENSUS, revisions: REVISIONS, freshness: FRESHNESS })) {
    await page.route(`${BASE}/${name}`, (route) => {
      expect(route.request().method()).toBe("GET");
      expect(route.request().headers()["x-nzstats-client"]).toBe("dashboard");
      return route.fulfill({ json: body });
    });
  }
});

test("the bank section renders, makes no write request and logs no page error", async ({ page }) => {
  const writes: string[] = [];
  const errors: string[] = [];
  page.on("request", (req) => { if (req.method() !== "GET") writes.push(req.url()); });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/economic-outlook");
  const section = page.getByRole("region", { name: "Bank outlooks" });
  await expect(section.getByRole("heading", { name: "Bank outlooks" })).toBeVisible();
  await expect(section).toContainText("Not independently reviewed");
  await expect(section.getByRole("article")).toHaveCount(3);
  await expect(section.getByRole("table", { name: /CPI inflation forecasts by bank/i })).toBeVisible();
  await expect(section.getByRole("table", { name: /source health/i })).toBeVisible();
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
});

test("the page has no horizontal scroll at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/economic-outlook");
  await expect(page.getByRole("heading", { name: "Bank outlooks" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});

test("the forecast table is reachable by keyboard and opens the evidence", async ({ page }) => {
  await page.goto("/economic-outlook");
  const cell = page.getByRole("button", { name: /Example Bank A.*Year to June 2027.*2\.1%/ });
  await cell.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("SYNTHETIC quote: inflation is forecast to ease");
  await expect(dialog).toContainText("verify-5");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(cell).toBeFocused();
});

test("dark mode renders the section readably", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/economic-outlook");
  const heading = page.getByRole("heading", { name: "Bank outlooks" });
  await expect(heading).toBeVisible();
  const [text, background] = await heading.evaluate((el) => [getComputedStyle(el).color, getComputedStyle(document.body).backgroundColor]);
  expect(text).not.toBe(background);
});

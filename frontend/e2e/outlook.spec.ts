import { expect, test } from "@playwright/test";
import { STATIC } from "./mode";

// The default deployment: public research is off (live) or absent (static). The page must still be complete and calm.
test("the economic outlook shows official indicators and explains that no research is published", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  // A disabled research API answers 404 by design; the browser logs that, and it is not a page error.
  page.on("console", (m) => m.type() === "error" && !/status of 404/.test(m.text()) && errors.push(m.text()));
  await page.goto("/economic-outlook");
  await expect(page.getByRole("heading", { level: 1, name: "Economic outlook" })).toBeVisible();
  const pulse = page.getByRole("list", { name: "Latest indicators" });
  await expect(pulse.getByRole("listitem")).toHaveCount(3);
  await expect(pulse).toContainText("Consumer prices were 4.1% higher than a year earlier");
  await expect(pulse).toContainText("Retail card spending was $");
  await expect(pulse).toContainText("Net migration added 20,350 people");
  await expect(page.getByText("No institutional research is published here yet")).toBeVisible();
  await expect(page.getByText(/No forecasts are published here yet/)).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("the research API is not reachable in the default deployment", async ({ request }) => {
  test.skip(STATIC, "the static site has no API at all (covered by the static network spec)");
  for (const path of ["/api/research/feed", "/api/research/forecasts", "/api/research/summaries/1"]) {
    const res = await request.get(path);
    expect(res.status(), path).toBe(404);
    expect(await res.json()).toEqual({ detail: "not found" });
  }
});

test("Outlook is a primary destination reachable from every page", async ({ page }, testInfo) => {
  await page.goto("/inflation");
  const nav = page.getByRole("navigation", { name: "Primary" });
  if (testInfo.project.name === "mobile") await nav.getByRole("button", { name: /Menu/ }).click();
  await nav.getByRole("link", { name: /^Outlook/ }).first().click();
  await expect(page).toHaveURL(/\/economic-outlook$/);
  await expect(page.getByRole("heading", { level: 1, name: "Economic outlook" })).toBeVisible();
});

test("a research address that is not published says so", async ({ page }) => {
  await page.goto("/economic-outlook/research/1");
  await expect(page.getByText("This research summary is not published here")).toBeVisible();
  await page.getByRole("link", { name: "Back to the economic outlook" }).click();
  await expect(page).toHaveURL(/\/economic-outlook$/);
});

test("no horizontal scroll on the economic outlook", async ({ page }) => {
  await page.goto("/economic-outlook");
  await page.waitForLoadState("networkidle");
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});

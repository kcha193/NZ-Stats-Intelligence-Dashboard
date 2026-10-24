import { expect, test } from "@playwright/test";

const manifest = async (page: import("@playwright/test").Page, change: (m: Record<string, unknown>) => void) =>
  page.route("**/data/v1/manifest.json", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    change(body);
    await route.fulfill({ response: res, json: body });
  });

test("a fixture build announces itself as test data on every page", async ({ page }) => {
  for (const route of ["/", "/inflation", "/stories/spending-retail-2026-09"]) {
    await page.goto(route);
    await expect(page.getByRole("note").filter({ hasText: "Test data built from fixture files" })).toBeVisible();
  }
});

test("a published build states when the data was last updated and that it is a snapshot", async ({ page }) => {
  await manifest(page, (m) => { m.origin = "production"; });
  for (const route of ["/", "/migration", "/stories/spending-retail-2026-09", "/health"]) {
    await page.goto(route);
    const stamp = page.locator("[data-snapshot-stamp]");
    await expect(stamp).toContainText("Data last updated 18 Oct 2026, 13:00 NZDT");
    await expect(stamp).toContainText("not a live feed");
    await expect(stamp).toBeInViewport();
  }
});

test("the page makes no live-data claims", async ({ page }) => {
  await manifest(page, (m) => { m.origin = "production"; });
  for (const route of ["/", "/health", "/inflation"]) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    // The stamp itself says "not a live feed"; everything else must make no such claim.
    const text = (await page.locator("body").innerText()).toLowerCase().replace("not a live feed", "");
    expect(text, route).not.toMatch(/real-time|realtime|live data|live feed|up to the minute|auto-refresh|updates automatically|automatic refresh/);
  }
});

test("the data health page reports freshness without a database flag or an ingestion log", async ({ page }) => {
  await page.goto("/health");
  await expect(page.getByRole("heading", { level: 1, name: "Data health" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Sources" })).toBeVisible();
  await expect(page.getByRole("table", { name: /recent ingestion runs/i })).toHaveCount(0);
  await expect(page.getByText(/Database (OK|unavailable)/)).toHaveCount(0);
});

import { expect, test } from "@playwright/test";
import { ALL_ROUTES } from "./helpers";

test("the public site only ever talks to its own origin and never to an API or a local backend", async ({ page, baseURL }) => {
  const origin = new URL(baseURL!).origin;
  const seen: { url: string; status: number }[] = [];
  page.on("response", (r) => seen.push({ url: r.url(), status: r.status() }));

  for (const route of ALL_ROUTES()) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
  }
  // Interactions that fetch more: calendar month view and a country chart.
  await page.goto("/calendar?view=month&month=2026-10");
  await page.waitForLoadState("networkidle");

  expect(seen.length).toBeGreaterThan(20);
  for (const { url, status } of seen) {
    const u = new URL(url);
    expect(u.origin, url).toBe(origin);
    expect(u.pathname, url).not.toMatch(/^\/api(\/|$)/);
    expect(status, url).toBeLessThan(400);
  }
  const data = seen.filter((s) => new URL(s.url).pathname.startsWith("/data/"));
  expect(data.length).toBeGreaterThan(5);
  expect(data.every((s) => new URL(s.url).pathname.startsWith("/data/v1/"))).toBe(true);
});

test("when the snapshot cannot be loaded the page says so instead of showing stale or empty numbers", async ({ page }) => {
  await page.route("**/data/v1/manifest.json", (route) => route.abort());
  await page.goto("/inflation");
  await expect(page.getByRole("alert")).toContainText("Data temporarily unavailable");
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("a response that is HTML instead of JSON is treated as unavailable", async ({ page }) => {
  await page.route("**/data/v1/cpi.json", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<html>app</html>" }));
  await page.goto("/inflation");
  await expect(page.getByRole("alert")).toContainText("Data temporarily unavailable");
});

test("data that Stats NZ has not published yet is shown as not published, not as an error", async ({ page }) => {
  await page.route("**/data/v1/ect.json", (route) => route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"not found"}' }));
  await page.goto("/electronic-card-transactions");
  await expect(page.getByText("Card transactions data has not been published yet")).toBeVisible();
  await expect(page.getByText("This could not be loaded.")).toHaveCount(0);
  await expect(page.getByText(/backfill|ingested/i)).toHaveCount(0);
});

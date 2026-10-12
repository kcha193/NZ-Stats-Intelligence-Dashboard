import { expect, test } from "@playwright/test";

test("overview shows KPIs, panels and no console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Economic overview" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Key indicators" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Upcoming releases" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("migration page renders charts on canvas and exports data", async ({ page }) => {
  await page.goto("/migration");
  await expect(page.getByRole("heading", { name: "International migration", level: 1 })).toBeVisible();
  await expect(page.locator("canvas").first()).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: /download data/i }).first().click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
});

test("client-side routes survive a reload and the API 404s as JSON", async ({ page, request }) => {
  await page.goto("/calendar");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Release calendar" })).toBeVisible();
  const res = await request.get("/api/nope");
  expect(res.status()).toBe(404);
  expect(res.headers()["content-type"]).toContain("application/json");
});

test("release analysis page and print layout", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /read the full release analysis/i }).click();
  await expect(page.getByRole("heading", { name: "Executive summary" })).toBeVisible();
  await page.emulateMedia({ media: "print" });
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
});

for (const route of ["/", "/migration", "/calendar", "/health"]) {
  test(`no horizontal scroll on ${route}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

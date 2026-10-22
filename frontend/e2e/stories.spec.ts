import { expect, test } from "@playwright/test";

test("homepage leads with a featured story that opens a complete story page", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/");
  const hero = page.getByRole("region", { name: /Annual inflation/ });
  await expect(hero.getByRole("group", { name: "Key statistic" })).toContainText("4.1%");
  await expect(hero.locator("canvas")).toBeVisible();
  await hero.getByRole("link", { name: "Read the story" }).click();
  await expect(page).toHaveURL(/\/stories\/inflation-annual-2026-06$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Annual inflation rises to 4.1%");
  await expect(page.getByRole("figure").locator("canvas")).toBeVisible();
  await expect(page.getByRole("region", { name: "Source" })).toContainText("21 Jul 2026");
  await expect(page.getByRole("link", { name: "Explore the inflation dashboard" })).toHaveAttribute("href", "/inflation");
  expect(errors).toEqual([]);
});

test("stories feed lists each category's stories and filters by category", async ({ page }) => {
  await page.goto("/stories");
  await expect(page.getByRole("heading", { level: 1, name: "Stories" })).toBeVisible();
  const all = page.getByRole("list", { name: "All stories" }).getByRole("article");
  await expect(all.first()).toBeVisible();
  await page.getByText(/^Inflation and prices \(\d+\)$/).click();
  await expect(page).toHaveURL(/category=inflation/);
  const inflation = page.getByRole("list", { name: "Inflation and prices stories" }).getByRole("article");
  await expect(inflation).toHaveCount(3);
});

test("a story address survives a reload and an old period is marked superseded", async ({ page }) => {
  await page.goto("/stories/inflation-drivers-2026-06");
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Transport");
  await page.goto("/stories/inflation-drivers-2026-03");
  await expect(page.getByRole("heading", { name: "This story has been superseded" })).toBeVisible();
});

for (const route of ["/stories", "/stories/inflation-annual-2026-06", "/stories/inflation-drivers-2026-06"]) {
  test(`no horizontal scroll on ${route}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

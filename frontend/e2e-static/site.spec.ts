import { expect, test } from "@playwright/test";
import { ALL_ROUTES, PAGES, STORIES } from "./helpers";

test.describe("every address works as a direct link and after a refresh", () => {
  for (const route of ALL_ROUTES()) {
    test(route, async ({ page }) => {
      const errors: string[] = [];
      page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
      page.on("pageerror", (e) => errors.push(String(e)));

      const first = await page.goto(route);
      expect(first?.status()).toBe(200);
      const served = (await first!.text()).match(/<title>(.*?)<\/title>/s)?.[1] ?? "";
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

      // The title a crawler reads in the HTML is the one the running app keeps.
      if (PAGES.includes(route) || STORIES.includes(route)) {
        await expect.poll(() => page.title()).toBe(served.replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/&quot;/g, '"'));
      }
      expect(await page.title()).not.toMatch(/^frontend$/i);

      const again = await page.reload();
      expect(again?.status()).toBe(200);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      expect(errors).toEqual([]);
    });
  }
});

test("an unknown address is a real 404 that still shows the site's own not-found message", async ({ page }) => {
  const res = await page.goto("/no-such-page");
  expect(res?.status()).toBe(404);
  await expect(page.getByText("That page does not exist")).toBeVisible();
});

test("an unknown story address is served the app, which explains it, rather than a bare 404", async ({ page }) => {
  const res = await page.goto("/stories/not-a-story-2020-01");
  expect(res?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("a missing data file is a JSON 404, never the app shell", async ({ request }) => {
  const res = await request.get("/data/v1/does-not-exist.json");
  expect(res.status()).toBe(404);
  expect(res.headers()["content-type"]).toContain("application/json");
});

for (const route of ["/", ...STORIES.slice(0, 2), "/calendar", "/migration"]) {
  test(`no horizontal scroll on ${route}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });
}

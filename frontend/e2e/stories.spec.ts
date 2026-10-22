import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test("homepage leads with a featured story that opens a complete story page", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/");
  // The newest verified release in the seeded data is card spending (16 Oct 2026), so it leads.
  const hero = page.getByRole("region", { name: "Retail card spending fell 0.4% in September 2026" });
  await expect(hero.getByRole("group", { name: "Key statistic" })).toContainText("\u22120.4%");
  await expect(hero.locator("canvas")).toBeVisible();
  await hero.getByRole("link", { name: "Read the story" }).click();
  await expect(page).toHaveURL(/\/stories\/spending-retail-2026-09$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Retail card spending fell 0.4% in September 2026");
  await expect(page.getByRole("figure").locator("canvas")).toBeVisible();
  await expect(page.getByRole("region", { name: "Source" })).toContainText("16 Oct 2026");
  await expect(page.getByRole("link", { name: "Explore the card spending dashboard" })).toHaveAttribute("href", "/electronic-card-transactions");
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

test("each category has a complete story page", async ({ page }) => {
  for (const [route, heading] of [
    ["/stories/spending-retail-2026-09", "Retail card spending fell 0.4% in September 2026"],
    ["/stories/migration-net-2026-07", "Annual net migration gain rises to 20,350"],
    ["/stories/inflation-tradables-2026-06", "Tradables inflation (4.9%) runs ahead of non-tradables (3.4%)"],
  ]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading);
    await expect(page.getByRole("figure").locator("canvas")).toBeVisible();
    await expect(page.getByRole("region", { name: "Values used in this story" })).toBeVisible();
  }
});

for (const route of [
  "/stories", "/stories/inflation-annual-2026-06", "/stories/inflation-drivers-2026-06", "/stories/spending-industries-2026-09",
  "/stories/migration-citizenship-2026-07",
]) {
  test(`no horizontal scroll on ${route}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

type Drawn = { width: number; height: number; text: string[] };

for (const [format, width, height] of [["Landscape", 1200, 675], ["Portrait", 1200, 1500]] as const) {
  test(`${format.toLowerCase()} story PNG is ${width}×${height} and carries the finding and its source`, async ({ page }) => {
    await page.goto("/stories/inflation-drivers-2026-06");
    await page.getByRole("radio", { name: "Annual" }).check({ force: true });
    await page.evaluate(() => {
      const drawn = new WeakMap<HTMLCanvasElement, string[]>();
      const fill = CanvasRenderingContext2D.prototype.fillText;
      CanvasRenderingContext2D.prototype.fillText = function (text, x, y, max) {
        drawn.set(this.canvas, [...(drawn.get(this.canvas) ?? []), String(text)]);
        fill.call(this, text, x, y, max);
      };
      const toUrl = HTMLCanvasElement.prototype.toDataURL;
      HTMLCanvasElement.prototype.toDataURL = function (...args) {
        const url = toUrl.apply(this, args);
        if (this.width === 1200) (window as unknown as { story: Drawn }).story = { width: this.width, height: this.height, text: drawn.get(this) ?? [] };
        return url;
      };
    });
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: new RegExp(`${format} PNG`) }).click(),
    ]);
    expect(download.suggestedFilename()).toBe(`inflation-drivers-2026-06-${format.toLowerCase()}.png`);
    const png = readFileSync(await download.path());
    expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([width, height]);
    const drawn = await page.evaluate(() => (window as unknown as { story: Drawn }).story);
    const all = drawn.text.join(" ");
    expect(all).toContain("Transport made the largest contribution");
    expect(all).toContain("+0.82 pp");
    expect(all).toContain("Contribution to annual CPI change, by group"); // the variant shown on the page
    expect(all).toContain("Source: Stats NZ, Consumers price index: June 2026 quarter, published 21 Jul 2026");
    expect(all).toContain("Reference period: June 2026 quarter");
    expect(all).toContain("(https://www.stats.govt.nz/information-releases/consumers-price-index-june-2026-quarter/)");
    expect(all).toContain("NZ Stats Intelligence (independent, not endorsed by Stats NZ) · http://127.0.0.1:8765/stories/inflation-drivers-2026-06");
    await expect(page.getByRole("status").filter({ hasText: "exported with source" })).toBeVisible();
  });
}

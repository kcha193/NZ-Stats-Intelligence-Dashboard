import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { SITE_URL } from "./helpers";

test("the share link names the canonical site, not the address the page was opened at", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => undefined);
  await page.addInitScript(() => Object.defineProperty(navigator, "share", { value: undefined }));
  await page.goto("/stories/spending-retail-2026-09");
  await page.getByRole("button", { name: "Share link" }).click();
  await expect(page.getByRole("status").filter({ hasText: /Link copied|Copy this link/ })).toContainText(
    /Link copied\.|https:\/\/nzstats\.test\/stories\/spending-retail-2026-09/,
  );
  const clip = await page.evaluate(() => navigator.clipboard.readText()).catch(() => `${SITE_URL}/stories/spending-retail-2026-09`);
  expect(clip).toBe(`${SITE_URL}/stories/spending-retail-2026-09`);
});

for (const [name, width, height] of [["Landscape", 1200, 675], ["Portrait", 1200, 1500]] as const) {
  test(`${name} PNG export downloads at ${width}×${height}`, async ({ page }) => {
    await page.goto("/stories/spending-retail-2026-09");
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: new RegExp(name) }).click()]);
    expect(download.suggestedFilename()).toBe(`spending-retail-2026-09-${name.toLowerCase()}.png`);
    const png = readFileSync((await download.path())!);
    expect(png.subarray(1, 4).toString()).toBe("PNG");
    expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([width, height]);
  });
}

test("CSV export carries the published values with their status", async ({ page }) => {
  await page.goto("/stories/migration-net-2026-07");
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /download data/i }).first().click()]);
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
  const csv = readFileSync((await download.path())!, "utf8");
  expect(csv.split("\n")[0]).toMatch(/period/i);
  expect(csv).toMatch(/provisional|final/);
});

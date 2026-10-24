import { expect, test } from "@playwright/test";

// The static site must look the same as the live app over the same data. The live app is the reference: its
// screenshot becomes this run's baseline, so no machine-specific images are committed. Only the snapshot stamp, which
// the live app does not have, is hidden. Health differs by design (no ingestion log) and is excluded.
const LIVE = process.env.LIVE_URL!;
const ROUTES = ["/", "/stories", "/stories/spending-retail-2026-09", "/stories/inflation-drivers-2026-06", "/inflation", "/electronic-card-transactions", "/migration", "/calendar"];

const settle = async (page: import("@playwright/test").Page, url: string) => {
  await page.goto(url);
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({ content: "[data-snapshot-stamp]{display:none !important}" });
  await page.waitForTimeout(250);
};

for (const route of ROUTES) {
  test(`looks the same as the live app: ${route}`, async ({ page, browser, baseURL }, testInfo) => {
    const liveContext = await browser.newContext(testInfo.project.use);
    const live = await liveContext.newPage();
    await settle(live, `${LIVE}${route}`);
    const baseline = await live.screenshot({ fullPage: true, animations: "disabled", scale: "css" });
    await liveContext.close();

    const name = `${route.replace(/\W+/g, "_") || "home"}.png`;
    const { writeFileSync, mkdirSync } = await import("node:fs");
    const { dirname } = await import("node:path");
    mkdirSync(dirname(testInfo.snapshotPath(name)), { recursive: true });
    writeFileSync(testInfo.snapshotPath(name), baseline);

    await settle(page, `${baseURL}${route}`);
    await expect(page).toHaveScreenshot(name, { fullPage: true, animations: "disabled", maxDiffPixelRatio: 0.002 });
  });
}

import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { ALL_ROUTES, STORIES } from "./helpers";

test("every kind of response carries the security and caching headers", async ({ request }) => {
  const asset = readFileSync(path.resolve(import.meta.dirname, "../dist-static/index.html"), "utf8").match(/\/assets\/[^"]+\.js/)![0];
  for (const url of ["/", STORIES[0], "/inflation", "/data/v1/manifest.json", "/data/v1/cpi.json", asset, "/no-such-page"]) {
    const h = (await request.get(url)).headers();
    expect(h["x-content-type-options"], url).toBe("nosniff");
    expect(h["x-frame-options"], url).toBe("DENY");
    expect(h["referrer-policy"], url).toBe("strict-origin-when-cross-origin");
    expect(h["strict-transport-security"], url).toContain("max-age=");
    const csp = h["content-security-policy"];
    expect(csp, url).toContain("default-src 'self'");
    expect(csp, url).toContain("frame-ancestors 'none'");
    expect(csp, url).not.toMatch(/script-src[^;]*unsafe/);
  }
  expect((await request.get(asset)).headers()["cache-control"]).toContain("immutable");
  expect((await request.get("/data/v1/manifest.json")).headers()["cache-control"]).toContain("must-revalidate");
  expect((await request.get("/data/v1/manifest.json")).headers()["x-robots-tag"]).toBe("noindex");
});

test("the Content-Security-Policy blocks nothing the pages, charts and exports need", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => undefined);
  await page.addInitScript(() => {
    (window as unknown as { __csp: string[] }).__csp = [];
    document.addEventListener("securitypolicyviolation", (e) =>
      (window as unknown as { __csp: string[] }).__csp.push(`${e.violatedDirective} ${e.blockedURI}`));
  });
  const messages: string[] = [];
  page.on("console", (m) => /Content Security Policy|Refused to/i.test(m.text()) && messages.push(m.text()));

  for (const route of ALL_ROUTES()) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
  }
  // Interactions: tooltips, a variant switch, a CSV download and a PNG export.
  await page.goto("/stories/inflation-drivers-2026-06");
  await page.getByRole("radio", { name: "Annual" }).check({ force: true });
  const canvas = page.getByRole("figure").locator("canvas");
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.move(box.x + box.width / 2 + 20, box.y + box.height / 2 + 5);
  await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /download data/i }).first().click()]);
  await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Landscape/ }).click()]);

  const violations = await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);
  expect(violations).toEqual([]);
  expect(messages).toEqual([]);
});

test("no page carries an inline script, which the policy would block", async ({ request }) => {
  for (const url of ["/", ...STORIES]) {
    const html = await (await request.get(url)).text();
    const inline = [...html.matchAll(/<script(?![^>]*\bsrc=)(?![^>]*application\/ld\+json)[^>]*>/g)];
    expect(inline, url).toEqual([]);
  }
});

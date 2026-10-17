import { expect, test } from "@playwright/test";

// Uses the same official-fixture database as smoke.spec.ts; no live source requests.
test("response time does not masquerade as data freshness", async ({ page }) => {
  await page.goto("/");
  // The fixture DB now includes ECT, captured after migration. Keep checking the capture time,
  // including its deterministic hour, rather than the response-generation time.
  await expect(page.getByText(/Data ingested 18 Oct 2026, 13:00 NZDT/)).toBeVisible();
  await expect(page.getByText(/Latest official Stats NZ statistics\. Updated/)).toHaveCount(0);
});

test("monthly uncertainty is explicitly a standard error", async ({ page }) => {
  await page.goto("/releases/2");
  const metrics = page.getByRole("table", { name: "Headline metrics", exact: true });
  await expect(metrics.getByText("SE 545", { exact: true })).toBeVisible();
  await expect(metrics.getByText(/±545/)).toHaveCount(0);
});

test("calendar details reveal a full title and restore keyboard focus", async ({ page }) => {
  await page.goto("/calendar?view=month&month=2026-10");
  const trigger = page.getByRole("button", { name: "Details for International migration: August 2026", exact: true });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "International migration: August 2026", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("14 Oct 2026, 10:45 NZDT", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Scheduled", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await expect(dialog).toBeHidden();
});

test("same-publication correction is separate and missing data is not zero", async ({ page, request }) => {
  const original = await (await request.get("/api/releases/2")).json();
  // Controlled response exercises added/withdrawn observations and a standard-error-only correction.
  original.analysis.corrections = {
    available: true, note: "Changes within this publication, separate from an earlier publication.",
    against_captured_at: "2026-10-11T16:00:00+13:00", captured_at: "2026-10-12T16:00:00+13:00",
    series: [{ series_key: "mig.m.net", label: "Net migration (monthly estimate)", unit: "people", n_changed: 2, changes: [
      { period: "2026-07", original: 5170, revised: 5170, original_status: "provisional", revised_status: "provisional", original_std_error: 545, revised_std_error: 546, original_released_in: "2026-07", revised_released_in: "2026-07" },
      { period: "2026-06", original: 2331, revised: null, original_status: "provisional", revised_status: null, original_std_error: 400, revised_std_error: null, original_released_in: "2026-07", revised_released_in: null },
    ] }],
  };
  await page.route("**/api/releases/2", (route) => route.fulfill({ json: original }));
  await page.goto("/releases/2");
  const section = page.locator("section", { has: page.getByRole("heading", { name: "Corrections within this publication", exact: true }) });
  await expect(section.getByText("SE 545 → SE 546", { exact: true })).toBeVisible();
  await expect(section.getByRole("cell", { name: "Not present", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Since the previous release", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});

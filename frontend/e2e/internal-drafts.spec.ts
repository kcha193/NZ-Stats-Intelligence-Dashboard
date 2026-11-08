import { expect, test } from "@playwright/test";
import { syntheticDraft, syntheticFeed } from "./fixtures/internal-drafts";
import { STATIC } from "./mode";

const emptyOutlook = "No evidence-supported AI outlook is available for this report.";

test.beforeEach(async ({ page }) => {
  test.skip(STATIC, "Internal commentary never appears on the static site.");
  await page.route("**/api/capabilities", (route) => route.fulfill({ json: { research_public: false, internal_drafts: true } }));
  await page.route("**/api/internal/drafts**", (route) => {
    expect(route.request().method()).toBe("GET");
    expect(route.request().headers()["x-nzstats-client"]).toBe("dashboard");
    const detail = /\/77$/.test(new URL(route.request().url()).pathname);
    return route.fulfill({ json: detail ? syntheticDraft : syntheticFeed });
  });
});

test("derived highlights exclude failures across executive, institutional and historical cards", async ({ page }) => {
  const writes: string[] = [];
  const errors: string[] = [];
  page.on("request", (req) => { if (req.method() !== "GET") writes.push(req.url()); });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/economic-outlook");
  for (const region of [page.getByRole("article", { name: "Executive summary" }), page.getByRole("article", { name: "Latest Reserve Bank commentary" }), page.getByRole("region", { name: "Other current commentary" }), page.getByRole("region", { name: "Historical commentary" })]) {
    await expect(region).toContainText(emptyOutlook);
    await expect(region).not.toContainText("Synthetic recovery outlook.");
  }
  const drivers = page.getByRole("region", { name: "Key economic drivers and risks" });
  await expect(drivers).toContainText("Statements with no automated issue detected");
  await expect(drivers).toContainText("Statements with automated warnings");
  await expect(drivers).toContainText("Synthetic definition remains uncertain.");
  const figures = page.getByRole("region", { name: "Reported economic facts and institutional forecasts" });
  for (const text of ["20 USD billion", "Quarterly change", "Seasonally adjusted", "Example Survey", "September 2026", "Provisional", "29 Oct 2026", "Example Institute", "2027 calendar year", "Annual growth", "Conditional"]) await expect(figures).toContainText(text);
  for (const text of ["Synthetic excluded figure.", "Synthetic unsupported policy decision.", "NZ$"]) await expect(figures).not.toContainText(text);

  const attention = page.getByRole("group", { name: "Claims requiring attention: Synthetic research update", exact: true });
  await expect(attention.getByText("Synthetic recovery outlook.", { exact: true })).not.toBeVisible();
  await attention.locator("summary").click();
  for (const text of ["Synthetic recovery outlook.", "Synthetic source quotation only.", "quote_not_found", "decision_not_in_evidence", "Excluded from executive insights", "verify-5", "8 Nov 2026", "Quote cited by the AI, not confirmed"]) await expect(attention).toContainText(text);
  await expect(attention.getByText("Synthetic recovery outlook.", { exact: true })).toBeVisible();
  await attention.getByRole("link", { name: "Complete original summary and stored assessment" }).click();
  await expect(page.getByRole("heading", { name: "Original stored summary" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Outlook", exact: true })).toContainText("No automated issue detected");
  const identity = page.getByRole("region", { name: "Derived presentation assessment", exact: true });
  await identity.locator("summary").click();
  await expect(identity).toContainText(syntheticDraft.assessment!.original_output_hash);
  await expect(identity).toContainText("Original stored assessment: verify-4");
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
});

test("a missing replay withholds highlights while the complete original remains reachable", async ({ page }) => {
  await page.route("**/api/internal/drafts**", (route) => route.fulfill({ json: { ...syntheticFeed, items: [{ ...syntheticDraft, assessment: null }] } }));
  await page.goto("/economic-outlook");
  const summary = page.getByRole("article", { name: "Executive summary" });
  await expect(summary).toContainText(emptyOutlook);
  await expect(summary).toContainText("Unavailable. Executive highlights are withheld.");
  await expect(summary).not.toContainText("Synthetic recovery outlook.");
  await expect(summary.getByRole("link", { name: "Read the full analysis, its evidence and its checks" })).toHaveAttribute("href", "/economic-outlook/draft/77");
});

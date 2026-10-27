import { expect, test, type Page } from "@playwright/test";

// SYNTHETIC research: four fictional institutions (eight published documents), served by the real API with public
// research switched on, over the real Stats NZ CPI fixture releases.
const SHOTS = process.env.OUTLOOK_SCREENSHOTS; // a directory: also save full-page review screenshots there

const noHorizontalScroll = async (page: Page) =>
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

async function open(page: Page, path = "/economic-outlook") {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  return errors;
}

test("published research appears with its labels; rejected and unreviewed summaries never do", async ({ page }) => {
  const responses: string[] = [];
  page.on("response", async (r) => r.url().includes("/api/research/") && responses.push(await r.text()));
  const errors = await open(page);
  const research = page.getByRole("region", { name: "Institutional research" });
  await expect(research.getByRole("article")).toHaveCount(8);
  await expect(research.getByRole("article", { name: "Quarterly Economic Outlook, October 2026 (synthetic)" }))
    .toContainText("AI interpretation of the document. Not an official statistic.");
  for (const hidden of ["REJECTED", "UNREVIEWED", "PRIVATE", "Private Reviewer", "RAW MODEL OUTPUT"]) {
    await expect(page.getByText(hidden)).toHaveCount(0);
    expect(responses.join("\n")).not.toContain(hidden);
  }
  await noHorizontalScroll(page);
  expect(errors).toEqual([]);
});

test("filters, search and grouping narrow the feed", async ({ page }) => {
  await open(page);
  const research = page.getByRole("region", { name: "Institutional research" });
  await research.getByRole("combobox", { name: "Institution" }).selectOption("kauri");
  await expect(research.getByRole("article")).toHaveCount(2);
  await expect(research).toContainText("Showing 1 to 2 of 2");
  await research.getByRole("combobox", { name: "Institution" }).selectOption("");
  await research.getByRole("searchbox", { name: "Search titles and summaries" }).fill("dairy");
  await expect(research.getByRole("article")).toHaveCount(1);
  await research.getByRole("searchbox", { name: "Search titles and summaries" }).fill("nothing like this");
  await expect(research.getByText("No research matches these filters.")).toBeVisible();
  await research.getByRole("button", { name: "Clear search and filters" }).click();
  await expect(research.getByRole("article")).toHaveCount(8);
  await research.getByRole("group", { name: "Group by" }).getByText("Institution").click();
  await expect(research.getByRole("region", { name: "Tasman Markets (synthetic)" })).toBeVisible();
});

test("forecasts are compared like with like, with a table and the official observation", async ({ page }) => {
  await open(page);
  const section = page.getByRole("region", { name: "Forecast comparison" });
  const cpi = section.getByRole("figure", { name: /CPI inflation, Year to June 2027/ }).filter({ hasText: "through the year" });
  await expect(cpi.locator("canvas")).toHaveCount(1);
  await expect(cpi).toContainText("Latest official observation: Stats NZ annual CPI inflation 4.1%");
  await cpi.getByText("Table view").click();
  await expect(cpi.getByRole("table").getByRole("row")).toHaveCount(4);
  // Hovering a mark shows its tooltip.
  const box = (await cpi.locator("canvas").boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await section.getByRole("group", { name: "Indicator" }).getByText("GDP", { exact: true }).click();
  await expect(section.getByRole("figure", { name: /GDP, Year to March 2027/ })).toHaveCount(2);
  await section.getByText(/Not compared \(2\)/).click();
  await expect(section).toContainText("annual average or a change through the year");
  await noHorizontalScroll(page);
});

test("forecast history and the CPI track record, with explicit states", async ({ page }) => {
  const errors = await open(page);
  await expect(page.getByRole("region", { name: "Forecast comparison" })).toContainText("Agreement: 3 institutions, median 2.3%");
  const track = page.getByRole("region", { name: "Forecast history and track record" });
  const panels = track.getByRole("figure", { name: /Year to June 2027$/ });
  await expect(panels).toHaveCount(3);
  await expect(panels.locator("canvas")).toHaveCount(3);
  await expect(track).toContainText("Changes of measure (not revisions)");
  await expect(track).toContainText("5 forecasts matched to an official outcome");
  await expect(track.getByRole("figure", { name: "Forecast minus first-published outcome" }).locator("canvas")).toHaveCount(1);
  await expect(track).toContainText(/No ranking/);
  await track.getByLabel("Target").selectOption("cpi_inflation|percent|annual_change|year_to:2026-06|central");
  await expect(track).toContainText("Official outcome (first published)");
  await page.getByRole("region", { name: "Forecast comparison" }).getByRole("group", { name: "Indicator" }).getByText("GDP", { exact: true }).click();
  await expect(track).toContainText("No official GDP series is ingested here");
  await noHorizontalScroll(page);
  expect(errors).toEqual([]);
});

test("the keyboard reaches the disclosure and the research detail, which shows its evidence", async ({ page }) => {
  await open(page);
  const entry = page.getByRole("article", { name: "Quarterly Economic Outlook, October 2026 (synthetic)" });
  const toggle = entry.getByRole("button", { name: /drivers, risks and uncertainty/ }); // "Show" becomes "Hide"
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(entry).toContainText("Uncertainty about the housing market remains high.");
  await entry.getByRole("link", { name: "Evidence and 4 forecasts" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "Quarterly Economic Outlook, October 2026 (synthetic)" })).toBeVisible();
  await expect(page.locator("blockquote").first()).toContainText("Annual CPI inflation is forecast to ease to 2.3%");
  await expect(page.getByRole("table", { name: "Forecast claims in this document" })).toContainText("Scenario: Downside");
  await noHorizontalScroll(page);
});

test("a summary-level source shows evidence locations without quotes", async ({ page }) => {
  await open(page);
  await page.getByRole("article", { name: /Fiscal and Economic Update/ }).getByRole("link", { name: /Evidence/ }).click();
  await expect(page.getByText(/does not permit quoting/)).toBeVisible();
  await expect(page.locator("blockquote")).toHaveCount(0);
});

test("review screenshots, light and dark", async ({ browser }, testInfo) => {
  test.skip(!SHOTS, "set OUTLOOK_SCREENSHOTS to a directory to save them");
  for (const scheme of ["light", "dark"] as const) {
    const ctx = await browser.newContext({ ...testInfo.project.use, colorScheme: scheme, deviceScaleFactor: 1 });
    const p = await ctx.newPage();
    await p.goto(`${testInfo.project.use.baseURL}/economic-outlook`);
    await p.getByRole("figure").first().waitFor();
    await p.evaluate(() => document.fonts.ready);
    await p.screenshot({ path: `${SHOTS}/outlook-${testInfo.project.name}-${scheme}.png`, fullPage: true });
    const track = p.getByRole("region", { name: "Forecast history and track record" });
    await track.getByRole("figure", { name: "Forecast minus first-published outcome" }).locator("canvas").waitFor();
    await track.screenshot({ path: `${SHOTS}/track-${testInfo.project.name}-${scheme}.png` });
    await p.getByRole("region", { name: "Forecast comparison" }).screenshot({ path: `${SHOTS}/comparison-${testInfo.project.name}-${scheme}.png` });
    if (scheme === "light") {
      await p.getByRole("link", { name: "Evidence and 4 forecasts" }).click();
      await p.getByRole("heading", { level: 2, name: "Provenance" }).waitFor();
      await p.screenshot({ path: `${SHOTS}/detail-${testInfo.project.name}.png`, fullPage: true });
    }
    await ctx.close();
  }
});

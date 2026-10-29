import { expect, test } from "@playwright/test";

test("homepage layers: glance, lead story, collection, topics, indicators, then releases", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/");
  const glance = page.getByRole("region", { name: "The economy at a glance" });
  await expect(glance.getByRole("article")).toHaveCount(3);
  await expect(glance.getByRole("article", { name: "Inflation" })).toContainText("Consumer prices were 4.1% higher than a year earlier.");
  await expect(glance.getByRole("article", { name: "Retail card spending" })).toContainText("Previous month: −0.9% (August 2026)");
  await expect(glance.getByRole("article", { name: "Net migration" })).toContainText("Provisional");
  await expect(page.getByRole("list", { name: "Latest stories" }).getByRole("article")).toHaveCount(7);
  await expect(page.getByRole("region", { name: "Explore by topic" })).toBeVisible();

  const indicators = page.getByRole("region", { name: "Key indicators" });
  // Phase 4C: GDP and labour market groups join the three topic groups (one headline each when collapsed).
  await expect(indicators.getByRole("article")).toHaveCount(5);
  await indicators.getByRole("button", { name: "Explore all 12 indicators" }).click();
  await expect(indicators.getByRole("article")).toHaveCount(12);
  await expect(page.getByRole("region", { name: "Data freshness" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("a key term opens a plain-language explainer and closes with Escape", async ({ page }) => {
  await page.goto("/");
  const term = page.getByRole("region", { name: "The economy at a glance" }).getByRole("button", { name: /annual change in consumer prices\s*: what does this mean/ });
  await term.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("consumers price index");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(term).toBeFocused();
});

test("navigation reaches every dashboard from the keyboard", async ({ page }, testInfo) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Primary" });
  const toggle = nav.getByRole("button", { name: testInfo.project.name === "mobile" ? /Menu/ : /Explore data/ });
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  if (testInfo.project.name === "mobile") await expect(nav.getByRole("link", { name: /^Stories/ })).toBeVisible();
  await nav.getByRole("link", { name: /^Card spending/ }).click();
  await expect(page).toHaveURL(/\/electronic-card-transactions$/);
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await page.keyboard.press("Escape");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toBeFocused();
});

test("story pages offer related stories and next/previous navigation", async ({ page }) => {
  await page.goto("/stories/spending-retail-2026-09");
  const related = page.getByRole("list", { name: "Related stories" }).getByRole("article");
  await expect(related).toHaveCount(3);
  await expect(related.first()).toContainText("Consumer spending");
  await page.getByRole("navigation", { name: "Story navigation" }).getByRole("link", { name: /Next story/ }).click();
  await expect(page).toHaveURL(/\/stories\/spending-industries-2026-09$/);
  await expect(page.getByRole("figure").locator("canvas")).toBeVisible();
});

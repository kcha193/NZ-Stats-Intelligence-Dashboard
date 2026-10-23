import { expect, test } from "@playwright/test";

test("overview shows KPIs, panels and no console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "New Zealand’s economy, explained." })).toBeVisible();
  await expect(page.getByRole("region", { name: "The economy at a glance" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Key indicators" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Upcoming releases" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("migration page renders charts on canvas and exports data", async ({ page }) => {
  await page.goto("/migration");
  await expect(page.getByRole("heading", { name: "International migration", level: 1 })).toBeVisible();
  await expect(page.locator("canvas").first()).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: /download data/i }).first().click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
});

test("client-side routes survive a reload and the API 404s as JSON", async ({ page, request }) => {
  await page.goto("/calendar");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Release calendar" })).toBeVisible();
  const res = await request.get("/api/nope");
  expect(res.status()).toBe(404);
  expect(res.headers()["content-type"]).toContain("application/json");
});

test("release analysis page and print layout", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /read the full release analysis/i }).click();
  await expect(page.getByRole("heading", { name: "Executive summary" })).toBeVisible();
  await page.emulateMedia({ media: "print" });
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
});

for (const route of ["/", "/migration", "/calendar", "/health"]) {
  test(`no horizontal scroll on ${route}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

test("country PNG includes a readable source caption and CSV identifies the bundle", async ({ page }, testInfo) => {
  await page.goto("/migration");
  const country = page.getByRole("figure").filter({ has: page.getByRole("heading", { name: /^Migrant arrivals by country/ }) });
  await expect(country.getByRole("link", { name: /International migration: July 2026/ })).toBeVisible();
  const data = await (await page.request.get("/api/migration/countries")).json();
  const provenance = data.provenance;
  await page.evaluate(() => {
    const captions = new WeakMap<HTMLCanvasElement, { text: string; x: number; y: number; width: number }[]>();
    const originalText = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText = function(text, x, y, maxWidth) {
      const transform = this.getTransform();
      const drawn = captions.get(this.canvas) ?? [];
      drawn.push({ text, x: x * transform.a, y: y * transform.d, width: this.measureText(text).width * transform.a });
      captions.set(this.canvas, drawn);
      originalText.call(this, text, x, y, maxWidth);
    };
    const originalUrl = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(...args) {
      const result = originalUrl.apply(this, args);
      (window as unknown as { pngCaption: unknown }).pngCaption = {
        width: this.width, height: this.height, drawn: captions.get(this) ?? [], url: result,
      };
      return result;
    };
  });
  const [image] = await Promise.all([
    page.waitForEvent("download"),
    country.getByRole("button", { name: /export image/i }).click(),
  ]);
  expect(image.suggestedFilename()).toBe("arrivals-by-country.png");
  const png = await page.evaluate(() => (window as unknown as { pngCaption: { width: number; height: number; drawn: { text: string; x: number; y: number; width: number }[]; url: string } }).pngCaption);
  const printed = png.drawn.map((line) => line.text);
  expect(printed.join("")).toContain(provenance.source_url);
  expect(printed.join(" ")).toContain("published 14 Sep 2026");
  expect(printed.join(" ")).toContain("Derived: Stats NZ");
  expect(printed.join(" ")).toContain(provenance.captured_at);
  // Text must be inside the actual exported bitmap, below the 420px chart (2x export).
  expect(png.drawn.every((line) => line.y >= 840 && line.y + 28 <= png.height && line.x >= 0 && line.x + line.width <= png.width)).toBe(true);
  const pixels = await page.evaluate(async (url) => {
    const img = new Image(); img.src = url; await img.decode();
    const canvas = document.createElement("canvas"); canvas.width = img.width; canvas.height = img.height;
    const ctx = canvas.getContext("2d")!; ctx.drawImage(img, 0, 0);
    const bytes = ctx.getImageData(0, 840, img.width, img.height - 840).data;
    const colours = new Set<string>();
    for (let i = 0; i < bytes.length; i += 4) colours.add(`${bytes[i]},${bytes[i+1]},${bytes[i+2]}`);
    return colours.size;
  }, png.url);
  expect(pixels).toBeGreaterThan(10);
  const pngPath = testInfo.outputPath("country-provenance.png");
  await image.saveAs(pngPath);
  await testInfo.attach("country provenance PNG", { path: pngPath, contentType: "image/png" });
  const [csv] = await Promise.all([page.waitForEvent("download"), country.getByRole("button", { name: /download data/i }).click()]);
  const stream = await csv.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const text = Buffer.concat(chunks).toString("utf8");
  for (const field of ["period_start", "period_end", "total_arrivals", "release_key", "source_url", "published_at", "captured_at", "bundle_sha256", "derivation_note"]) expect(text).toContain(field);
  expect(text).toContain(provenance.bundle_sha256);
  expect(text).toContain(provenance.source_url);
  await country.getByText("View data table").click();
  await expect(country.getByRole("table")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});

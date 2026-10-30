import { expect, test, type Page, type Route } from "@playwright/test";
import { STATIC } from "./mode";

// The test servers run offline (`--no-scheduler`), so they never contact Stats NZ. The on-open states are played
// back by intercepting the two refresh routes; everything else is the real app and its stored data.

const base = {
  mode: "on_open", state: "completed", phase: null, run_id: 7, trigger: "open",
  started_at: "2026-10-30T09:00:00+13:00", finished_at: "2026-10-30T09:01:00+13:00",
  last_success_at: "2026-10-30T09:01:00+13:00", discovered: 0, ingested: 0, unchanged: 0, requests: 4,
  failures: [], pending: [], error_class: null, data_version: "a1", started: false,
  latest: [{ series_slug: "international-migration", label: "International migration", reference_period: "2026-07",
    period_label: "July 2026", published_at: "2026-09-14T10:45:00+12:00" }],
};

async function playBack(page: Page, post: object[], status: object[]) {
  const posts: unknown[] = [];
  const next = (q: object[]) => (q.length > 1 ? q.shift()! : q[0]);
  const reply = (route: Route, body: object) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...base, ...body }) });
  await page.route("**/api/refresh", (route) => {
    posts.push(route.request().postDataJSON());
    return reply(route, next(post));
  });
  await page.route("**/api/refresh/status", (route) => reply(route, next(status)));
  return posts;
}

const indicator = (page: Page) => page.getByRole("button", { name: /data refresh/i });

test("an offline dashboard shows no refresh indicator and sends no check to Stats NZ", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (r) => requests.push(`${r.method()} ${new URL(r.url()).pathname}`));
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(indicator(page)).toHaveCount(0);
  // Live: one local request that the offline server answers with mode "off". Static: none at all.
  expect(requests.filter((r) => r === "POST /api/refresh")).toHaveLength(STATIC ? 0 : 1);
  expect(requests.filter((r) => !r.startsWith("GET /") && r !== "POST /api/refresh")).toEqual([]);
});

test.describe("on-open refresh", () => {
  test.skip(STATIC, "the published site is a snapshot: it never checks Stats NZ");

  test("checks once on open, keeps the stored data on screen and navigable, then says it updated", async ({ page }) => {
    const posts = await playBack(
      page,
      [{ started: true, state: "running", phase: "checking" }],
      [
        { state: "running", phase: "downloading" },
        { state: "running", phase: "downloading" },
        { state: "running", phase: "validating" },
        { ingested: 1, data_version: "a2" },
      ],
    );
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: /Checking for updates|Downloading latest release/ })).toBeAttached();
    // Navigation works while the server ingests; there is no full-page spinner in the way.
    await page.getByRole("list", { name: "All pages" }).getByRole("link", { name: "Stories" }).click();
    await expect(page).toHaveURL(/\/stories$/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "Updated with new data" })).toBeAttached({ timeout: 15_000 });
    expect(posts).toEqual([{ manual: false }]); // one automatic check for the whole visit, not one per page
  });

  test("says when the data is already current, and offers Check now", async ({ page }) => {
    const posts = await playBack(page, [{}, { started: true, state: "running", phase: "checking" }], [{}]);
    await page.goto("/inflation");
    await expect(page.getByRole("status").filter({ hasText: "Data is up to date" })).toBeAttached();
    await indicator(page).click();
    await expect(page.getByText("Latest statistics held (reference period, published)")).toBeVisible();
    await expect(page.getByText(/Last successful check/)).toBeVisible();
    await page.getByRole("button", { name: "Check now" }).click();
    await expect.poll(() => posts).toEqual([{ manual: false }, { manual: true }]);
  });

  test("a failed check says the last verified data is shown", async ({ page }) => {
    await playBack(page, [{ state: "failed", error_class: "network" }], [{ state: "failed" }]);
    await page.goto("/");
    await expect(page.getByRole("status").filter({ hasText: "Could not refresh — showing last verified data" })).toBeAttached();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("the indicator fits the header without horizontal scrolling", async ({ page }) => {
    await playBack(page, [{}], [{}]);
    await page.goto("/");
    await expect(indicator(page)).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

import { expect, test, type Page } from '@playwright/test';
import september from '../src/test/fixtures/ect.json' with { type: 'json' };
import { STATIC } from './mode';

// Browser-only synthetic October response. No claim about official October figures.
// The backend rehearsal separately verifies real parsing/commit against source bytes.
function syntheticOctober() {
  const data = structuredClone(september);
  const release = data.analysis.release;
  release.title = 'Electronic card transactions: October 2026';
  release.release_key = 'electronic-card-transactions:october 2026';
  release.period_label = 'October 2026';
  release.published_at = '2026-11-12T10:45:00+13:00';
  release.headline = 'SYNTHETIC OCTOBER REHEARSAL — NOT OFFICIAL DATA';
  release.page_url = 'https://www.stats.govt.nz/information-releases/SYNTHETIC-ect-october/';
  data.analysis.executive_summary = [];
  data.analysis.context = [];
  data.analysis.revisions.note = 'Synthetic revision information; earlier vintages are preserved.';
  data.analysis.vintage_captured_at = release.published_at;
  for (const metric of data.analysis.headline_metrics) {
    if (metric.frequency !== 'monthly') continue;
    metric.period = '2026-10';
    metric.period_label = 'October 2026';
    metric.status = 'provisional';
    if (metric.change_prior) Object.assign(metric.change_prior, {
      absolute: 0, percent: 0, comparison_period: '2026-09', label: 'vs September 2026',
    });
  }
  for (const s of data.series) {
    Object.assign(s.vintage, { release_key: release.release_key, title: release.title,
      published_at: release.published_at, captured_at: release.published_at });
    s.source_url = 'https://www.stats.govt.nz/assets/Uploads/SYNTHETIC/electronic-card-transactions-october-2026.zip';
    if (s.series.frequency === 'monthly') {
      s.series.latest_period = '2026-10';
      s.points.push({ ...s.points.at(-1)!, period: '2026-10', status: 'provisional' });
    }
  }
  return data;
}

const status = {
  mode: 'on_open', state: 'completed', phase: null, run_id: 1, trigger: 'open',
  started_at: '2026-11-12T10:45:00+13:00', finished_at: '2026-11-12T10:46:00+13:00',
  last_success_at: '2026-11-12T10:46:00+13:00', discovered: 0, ingested: 0,
  unchanged: 0, requests: 4, failures: [], pending: [], error_class: null,
  data_version: 'a1', started: false, latest: [],
};

const diagnostics = new WeakMap<Page, { errors: string[]; external: string[] }>();

test.describe('Phase 4Y synthetic October acceptance', () => {
  test.skip(STATIC, 'static isolation is covered by the existing snapshot suite');

  test.beforeEach(async ({ context, page }) => {
    const external: string[] = [];
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    await context.route('**/*', route => {
      if (!['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname)) {
        external.push(route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    test.info().annotations.push({ type: 'fixture', description: 'SYNTHETIC OCTOBER; offline server' });
    diagnostics.set(page, { errors, external });
  });

  test.afterEach(async ({ page }) => {
    expect(diagnostics.get(page)!.errors).toEqual([]);
    expect(diagnostics.get(page)!.external).toEqual([]);
  });

  test('committed vintage refreshes ECT charts and exports without a reload', async ({ page }, info) => {
    let posts = 0;
    let ectReads = 0;
    let commit = false;
    let heldOctober = false;
    await page.route('**/api/ect', route => {
      ectReads++;
      return route.fulfill({ json: heldOctober ? syntheticOctober() : september });
    });
    await page.route('**/api/refresh', route => {
      posts++;
      return route.fulfill({ json: { ...status, state: 'running', phase: 'checking', started: true } });
    });
    await page.route('**/api/refresh/status', route => {
      if (commit) heldOctober = true;
      return route.fulfill({ json: { ...status, ...(heldOctober
        ? { ingested: 1, data_version: 'a2' }
        : posts ? { state: 'running', phase: 'validating' } : {}) } });
    });
    await page.goto('/electronic-card-transactions');
    await expect(page.getByText(/Latest reference period: September 2026/)).toBeVisible();
    await expect.poll(() => posts).toBe(1);
    commit = true;
    await expect(page.getByText(/Latest reference period: October 2026/)).toBeVisible();
    await expect(page.getByText(/Published 12 Nov 2026, 10:45/)).toBeVisible();
    await expect(page.getByRole('status').filter({ hasText: 'Updated with new data' })).toBeAttached();
    expect(ectReads).toBeGreaterThanOrEqual(2);
    expect(posts).toBe(1);
    await expect(page.getByRole('link', { name: 'Official Stats NZ release' })).toHaveAttribute('href', /SYNTHETIC/);
    await expect(page.getByText(/Synthetic revision information/)).toBeVisible();
    await page.getByText('View data table').first().click();
    await expect(page.getByRole('table').first()).toContainText('Oct 2026');
    const [download] = await Promise.all([page.waitForEvent('download'),
      page.getByRole('button', { name: /download data/i }).first().click()]);
    const stream = await download.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
    const csv = Buffer.concat(chunks).toString('utf8');
    expect(csv).toContain('2026-10');
    expect(csv).toContain('provisional');
    expect(csv).toContain('NZD million');
    expect(csv).toContain('electronic-card-transactions:october 2026');
    await page.getByText('View data table').first().click();
    await page.screenshot({ path: info.outputPath('synthetic-october-monthly.png'), fullPage: true });
    for (const adjustment of ['actual', 'trend']) {
      await page.getByRole('combobox', { name: 'Adjustment', exact: true }).selectOption(adjustment);
      await expect(page.getByRole('heading', { name: new RegExp(`Retail spending · ${adjustment === 'actual' ? 'Actual' : 'Trend'} · monthly`) })).toBeVisible();
    }
    await page.getByRole('group', { name: 'ECT frequency' }).getByText('Quarterly', { exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Industry performance · quarterly change' })).toBeVisible();
    await expect(page.getByText(/Quarter ended Sep 2026:/).first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    await page.screenshot({ path: info.outputPath('synthetic-october.png'), fullPage: true });
  });

  for (const outcome of ['pending', 'rejected']) {
    test(`${outcome} October retains September and never claims current`, async ({ page }) => {
      const pending = [{ release_key: 'electronic-card-transactions:october 2026',
        reason: outcome === 'pending' ? 'not_published_yet' : 'rejected_today',
        series_slug: 'electronic-card-transactions', label: 'Electronic card transactions',
        reference_period: '2026-10', period_label: 'October 2026',
        published_at: '2026-11-12T10:45:00+13:00' }];
      const result = { ...status, pending, failures: outcome === 'rejected'
        ? [{ key: pending[0].release_key, outcome: 'failed', error_class: 'validation_failed' }] : [] };
      await page.route('**/api/refresh**', route => route.fulfill({ json: result }));
      await page.goto('/electronic-card-transactions');
      await expect(page.getByText(/Latest reference period: September 2026/)).toBeVisible();
      await expect(page.getByRole('status').filter({ hasText: outcome === 'pending' ? /pending/ : /Could not refresh — showing last verified data/ })).toBeAttached();
      await expect(page.getByText('Data is up to date', { exact: true })).toHaveCount(0);
      await expect(page.locator('canvas').first()).toBeVisible();
    });
  }

  test('ECT loading state resolves to the stored release', async ({ page }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/ect', async route => {
      await gate;
      await route.fulfill({ json: september });
    });
    try {
      await page.goto('/electronic-card-transactions');
      await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible();
    } finally {
      release();
    }
    await expect(page.getByText(/Latest reference period: September 2026/)).toBeVisible();
    await expect(page.getByRole('status', { name: 'Loading', exact: true })).toHaveCount(0);
  });
});

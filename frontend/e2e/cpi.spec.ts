import { expect, test } from '@playwright/test';

test('inflation dashboard: KPIs, ranges, contributions, explorer, exports and no overflow', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/inflation');
  await expect(page.getByRole('heading', { level: 1, name: 'Inflation' })).toBeVisible();
  const kpis = page.getByRole('region', { name: 'CPI key indicators' });
  await expect(kpis).toContainText('4.1%');
  await expect(kpis).toContainText('1.5%');
  await expect(kpis).toContainText('+1.0 percentage points');
  await expect(page.locator('canvas').first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath(`cpi-${testInfo.project.name}.png`), fullPage: true });

  await page.getByRole('group', { name: 'History range' }).getByText('3 years', { exact: true }).click();
  await page.locator('canvas').first().hover({ position: { x: 200, y: 140 } });
  await page.getByRole('group', { name: 'Contribution horizon' }).getByText('Annual contribution', { exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Contribution to annual CPI change, by group' })).toBeVisible();
  await expect(page.getByText(/groups sum to 4\.00 against a headline change of 4\.06/)).toBeVisible();
  await page.getByLabel('CPI component').selectOption('transport');
  await page.getByRole('group', { name: 'Component view' }).getByText('Index', { exact: true }).click();
  await expect(page.getByRole('heading', { name: /Transport · index/ })).toBeVisible();

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: /download data/i }).first().click(),
  ]);
  expect(download.suggestedFilename()).toBe('cpi-annual-inflation.csv');
  const chunks: Buffer[] = [];
  for await (const chunk of (await download.createReadStream())!) chunks.push(Buffer.from(chunk));
  const csv = Buffer.concat(chunks).toString('utf8');
  expect(csv).toContain('annual_pct');
  expect(csv).toContain('CPIQ.SE9A');
  expect(csv.trim().split('\n')).toHaveLength(13); // 12 quarters plus the header
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  await page.getByRole('link', { name: 'Full release analysis', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Consumers price index: June 2026 quarter' })).toBeVisible();
  await expect(page.getByRole('table', { name: 'Headline metrics' })).toContainText('percentage points');
  expect(errors).toEqual([]);
});

test('overview shows the CPI indicator and links the inflation dashboard', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('article', { name: 'CPI annual inflation, all groups' })).toContainText('4.1%');
  await page.getByRole('link', { name: 'Explore inflation' }).click();
  await expect(page).toHaveURL(/\/inflation$/);
});

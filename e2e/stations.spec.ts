import { expect, test, type Page } from '@playwright/test';
import { axeClean, copyClean } from './checks';

const DAY = '2022-06-03'; // 44371 precursor: P1 is INVESTIGATE
const day = (d: string, n: number) => new Date(Date.parse(d) + n * 864e5).toISOString().slice(0, 10);

const open = async (page: Page) => {
  await page.goto('/');
  await expect(page.getByTestId('station-tile').first()).toBeVisible();
};
const goTo = async (page: Page, d: string) => {
  await page.getByTestId('scrubber-date').fill(d);
  await page.getByTestId('scrubber-date').press('Enter');
  await expect(page.getByTestId('scrubber-live-date')).toHaveText(d);
};
const openDrawer = async (page: Page) => {
  await page.getByRole('row', { name: /Investigate/ }).first().click();
  await expect(page.getByTestId('provenance')).toBeVisible();
};

test.describe('frame', () => {
  test('origin badge, "Data up to", never "now"', async ({ page }) => {
    await open(page);
    await expect(page.getByTestId('origin-badge')).toContainText('REPLAY');
    await expect(page.getByTestId('as-of-label')).toContainText('Data up to');
    expect(await page.getByTestId('as-of-label').innerText()).not.toMatch(/\bnow\b/i);
  });

  test('scrubber is disabled at both edges', async ({ page, request }) => {
    const { stations } = await (await request.get('/api/stations')).json();
    const min = stations.map((s: any) => s.as_of_min.slice(0, 10)).sort().pop();
    const max = stations.map((s: any) => s.as_of_max.slice(0, 10)).sort()[0];
    await open(page);
    await goTo(page, min);
    await expect(page.getByTestId('scrubber-prev')).toBeDisabled();
    await expect(page.getByTestId('scrubber-next')).toBeEnabled();
    await goTo(page, max);
    await expect(page.getByTestId('scrubber-next')).toBeDisabled();
    await expect(page.getByTestId('replay-toggle')).toBeDisabled();
  });

  test('arrow keys update the aria-live date', async ({ page }) => {
    await open(page);
    await page.getByRole('slider', { name: 'Scrub through days' }).press('ArrowRight');
    await expect(page.getByTestId('scrubber-live-date')).toHaveText(day(DAY, 1));
  });

  test('reduced motion: Replay does not auto-advance', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await open(page);
    await page.getByTestId('replay-toggle').click();
    await expect(page.getByTestId('scrubber-live-date')).toHaveText(day(DAY, 1));
    await page.waitForTimeout(2500);
    await expect(page.getByTestId('scrubber-live-date')).toHaveText(day(DAY, 1));
  });
});

test.describe('stations', () => {
  test('empty-queue text on a normal day', async ({ page, request }) => {
    const { stations } = await (await request.get('/api/stations')).json();
    let normal = '';
    for (let d = '2022-08-01'; !normal && d < '2022-12-31'; d = day(d, 3)) {
      const as = await Promise.all(
        stations.map(async (s: any) =>
          (await request.get(`/api/assess?station_id=${s.station_id}&as_of_utc=${d}T00:00:00Z`)).json(),
        ),
      );
      if (as.every((a: any) => a.queue.length === 0 && a.quality === 'SUFFICIENT')) normal = d;
    }
    expect(normal, 'a normal day exists in 2022-08..12').not.toBe('');
    await open(page);
    await goTo(page, normal);
    await expect(page.getByTestId('queue-empty')).toHaveText(`No pumps need attention as of ${normal}.`);
    await axeClean(page);
  });

  test('44371 P1 row names its status; Tab, Enter and Esc drive the drawer', async ({ page }) => {
    await open(page);
    const row = page.getByRole('row', { name: /Investigate/ }).first();
    await expect(row).toContainText('44371');
    for (let i = 0; i < 60 && !(await row.evaluate((e) => e === document.activeElement)); i++) await page.keyboard.press('Tab');
    await expect(row).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('drawer')).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('drawer')).toHaveCount(0);
    await expect(row).toBeFocused();
  });

  test('axe and copy scan: stations tab', async ({ page }) => {
    await open(page);
    await axeClean(page);
    await copyClean(page);
  });
});

test.describe('drawer', () => {
  test.beforeEach(async ({ page }) => {
    await open(page);
    await openDrawer(page);
  });

  test('shows model_version and source hash', async ({ page, request }) => {
    const h = await (await request.get('/api/health')).json();
    await expect(page.getByTestId('provenance-model-version')).toHaveText(h.model_version);
    await expect(page.getByTestId('provenance-source-hash')).toHaveText(h.source_hash);
  });

  test('Copy puts the work order on the clipboard', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.getByTestId('copy-work-order').click();
    const text = await page.evaluate(() => navigator.clipboard.readText());
    expect(text).toContain('Dragonfly draft - needs human review');
  });

  test('no API key: AI explanation unavailable', async ({ page }) => {
    await page.getByTestId('ask-input').fill('Why is this pump flagged?');
    await page.getByTestId('ask-submit').click();
    await expect(page.getByTestId('ask-offline')).toHaveText('AI explanation unavailable (no API key)');
  });

  test('axe and copy scan: open drawer', async ({ page }) => {
    await axeClean(page);
    await copyClean(page);
  });
});

test.describe('errors', () => {
  const fail500 = (page: Page) => page.route('**/api/assess*', (r) => r.fulfill({ status: 500, body: '{}' }));

  test('a 500 from /api/assess shows the error state; axe clean', async ({ page }) => {
    await fail500(page);
    await page.goto('/');
    await expect(page.getByTestId('state-error')).toBeVisible();
    await axeClean(page);
  });

  test('a 500 from /api/assess shows the server banner', async ({ page }) => {
    // UI BUG: App.tsx shows server-banner only when /api/stations fails; a 500 from /api/assess shows no banner (§10.1).
    test.fail();
    await fail500(page);
    await page.goto('/');
    await expect(page.getByTestId('server-banner')).toBeVisible();
  });
});

test.describe('mobile 390x844', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('no horizontal scroll; drawer is full-screen; axe', async ({ page }) => {
    await open(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await axeClean(page);
    await openDrawer(page);
    const box = (await page.getByTestId('drawer').boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(388);
    expect(box.height).toBeGreaterThanOrEqual(840);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await axeClean(page);
  });
});

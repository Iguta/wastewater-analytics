import { expect, test } from '@playwright/test';
import { axeClean, copyClean } from './checks';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('tab-lab').click();
  await expect(page.getByTestId('lab-compare-table')).toBeVisible();
});

test('A/B/C table equals /api/evaluation', async ({ page, request }) => {
  const { benchmarks: b } = await (await request.get('/api/evaluation')).json();
  const rate = (r: { k: number; n: number }) => `${r.k} of ${r.n}`;
  const expected = ['A', 'B', 'C'].map((k) => [
    rate(b[k].caught),
    b[k].median_lead_days == null ? 'n/a' : b[k].median_lead_days.toFixed(1),
    rate(b[k].false_storm),
    rate(b[k].false_duty),
    rate(b[k].false_transient),
    b[k].real_alerts_per_pump_6mo == null ? 'n/a' : b[k].real_alerts_per_pump_6mo.toFixed(2),
  ]);
  const rows = page.getByTestId('lab-compare-table').locator('tbody tr');
  await expect(rows).toHaveCount(3);
  const shown = await rows.evaluateAll((trs) => trs.map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent!.trim())));
  expect(shown).toEqual(expected);
});

test('axe and copy scan: lab tab', async ({ page }) => {
  await axeClean(page);
  await copyClean(page);
});

test('Break the level sensor: SENSOR_FAULT and "High-level check: unknown"', async ({ page, request }) => {
  const { dev_cases } = await (await request.get('/api/scenarios')).json();
  const id = dev_cases.find((c: any) => c.experiment === 'break_sensor').case_id;
  expect((await (await request.get(`/api/replay?case_id=${id}`)).json()).sensor_fault_flagged).toBe(true);
  await page.getByTestId('exp-break-sensor').click();
  await expect(page.locator('[data-experiment="break_sensor"]')).toContainText('Sensor fault flagged. High-level check: unknown');
});

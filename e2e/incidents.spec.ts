import { expect, test, type Page } from '@playwright/test';
import { axeClean, bannedWords, gallons, otherBanned } from './checks';

const MORNINGSIDE = 'bloomington_morningside_2024_04_11';

const incidents = async (page: Page) => {
  await page.goto('/');
  await page.getByTestId('tab-incidents').click();
  await expect(page.getByTestId('incident-card').first()).toBeVisible();
};
const morningside = (page: Page) => page.locator(`[data-testid="incident-card"][data-scenario-id="${MORNINGSIDE}"]`);

test('axe: incidents tab', async ({ page }) => {
  await incidents(page);
  await axeClean(page);
});

test('copy scan: incidents tab, banned words except "confirmed", and gallons labels', async ({ page }) => {
  await incidents(page);
  await bannedWords(page, otherBanned);
  await gallons(page);
});

test('copy scan: no "confirmed" in the facts', async ({ page }) => {
  await incidents(page);
  await bannedWords(page, 'confirmed');
});

test('Morningside A replay renders the failure marker and a warning or "did not warn"', async ({ page }) => {
  await incidents(page);
  await morningside(page).getByTestId('replay-variant-a').click();
  await expect(page.getByTestId('replay-banner')).toContainText('Variant A');
  // Jump to the last day, where the failure and trip have happened (rendering only, never the detection outcome).
  await page.getByRole('slider', { name: 'Scrub through days' }).press('End');
  await expect(page.getByTestId('failure-marker')).toBeVisible();
  await expect(page.getByTestId('trip-marker')).toBeVisible();
  await expect(page.getByTestId('replay-output')).toContainText(/First Investigate|did not warn before the trip/);
  await axeClean(page);
  await bannedWords(page, otherBanned);
  await gallons(page);
});

test('the A/B switch changes the replay', async ({ page }) => {
  await incidents(page);
  await morningside(page).getByTestId('replay-variant-a').click();
  await expect(page.getByTestId('replay-banner')).toContainText('Variant A');
  await page.getByTestId('tab-incidents').click();
  await morningside(page).getByTestId('replay-variant-b').click();
  await expect(page.getByTestId('replay-banner')).toContainText('Variant B');
});

test('"Moved up: storm ahead" appears (§4.12)', async ({ page }) => {
  // BACKEND GAP: assess.py always returns storm=None, so §4.12 never promotes a finding. The UI renders queue-moved-up from it.
  test.fail();
  await incidents(page);
  await morningside(page).getByTestId('replay-variant-a').click();
  await expect(page.getByTestId('replay-banner')).toBeVisible();
  await page.getByTestId('skip-to-investigate').click();
  await expect(page.getByTestId('queue-moved-up').first()).toBeVisible();
});

test('outcome gallons are all "Simulated:" after both replays', async ({ page }) => {
  // UI BUG: the outcome assumptions list shows "1500 gal" (usable storage, an UNVERIFIED assumption) with neither "Simulated:" nor "(record)".
  test.fail();
  await incidents(page);
  for (const v of ['a', 'b']) {
    await morningside(page).getByTestId(`replay-variant-${v}`).click();
    await expect(page.getByTestId('replay-banner')).toBeVisible();
    await page.getByTestId('tab-incidents').click();
  }
  await expect(page.getByTestId('simulated-gal').first()).toContainText('Simulated:');
  await gallons(page);
});

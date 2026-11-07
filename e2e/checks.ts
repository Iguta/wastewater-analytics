import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

export const axeClean = async (page: Page) => {
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(' | ')}`)).toEqual([]);
};

// §10.7 banned words.
export const bannedWords = async (page: Page) => {
  const text = await page.locator('body').innerText();
  expect(text.match(/probability|will fail|confirmed|saved|prevented|would have/gi) ?? []).toEqual([]);
};

// §11.1: every gallons figure is preceded by "Simulated:" or followed by "(record)".
export const gallons = async (page: Page) => {
  const text = await page.locator('body').innerText();
  const bad = [...text.matchAll(/\d[\d,]* gal\b/g)].filter(
    (m) =>
      !text.slice(Math.max(0, m.index - 12), m.index).includes('Simulated:') &&
      !text.slice(m.index, m.index + m[0].length + 9).includes('(record)'),
  );
  expect(bad.map((m) => m[0])).toEqual([]);
};

export const copyClean = async (page: Page) => {
  await bannedWords(page);
  await gallons(page);
};

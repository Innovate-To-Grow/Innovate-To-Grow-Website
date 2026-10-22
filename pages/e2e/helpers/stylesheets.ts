import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import type {Page} from '@playwright/test';

/**
 * The app shell mock (`./shell.ts`) answers `/layout/styles.css` with an empty sheet,
 * so specs that check what the redesign actually looks like (colours, fit, touch
 * targets) serve the CMS stylesheets seeded by the migrations instead.
 *
 * Only the content sheets are served. The component sheets ship with the frontend
 * bundle now, and their DB rows are on their way out, so leaving them out proves the
 * bundle styles the shell and the React pages on its own.
 *
 * `E2E_SEED_STYLESHEETS` may point at another stylesheets.json of the same shape,
 * which lets a sheet edit be checked before it is packed into the seed.
 */
const SEED_STYLESHEETS =
  process.env.E2E_SEED_STYLESHEETS ??
  resolve(dirname(fileURLToPath(import.meta.url)), '../../../src/apps/cms/migrations/data/stylesheets.json');

// Sheets whose rules moved into co-located CSS under pages/src.
const BUNDLED_SHEETS = new Set([
  'layout-container',
  'layout-menu',
  'layout-footer',
  'auth',
  'page-news',
  'page-projects',
  'page-events',
  'page-subscribe',
  'page-misc',
  'maintenance',
]);

interface SeedStylesheet {
  fields: {name: string; css: string; is_active: boolean; sort_order: number};
}

export function seedStylesheetCss(): string {
  const sheets = JSON.parse(readFileSync(SEED_STYLESHEETS, 'utf8')) as SeedStylesheet[];
  return sheets
    .filter((sheet) => sheet.fields.is_active && !BUNDLED_SHEETS.has(sheet.fields.name))
    .sort((left, right) => left.fields.sort_order - right.fields.sort_order)
    .map((sheet) => sheet.fields.css)
    .join('\n');
}

export async function serveSeedStylesheets(page: Page): Promise<void> {
  const css = seedStylesheetCss();
  await page.route('**/layout/styles.css*', (route) => route.fulfill({status: 200, contentType: 'text/css', body: css}));
}

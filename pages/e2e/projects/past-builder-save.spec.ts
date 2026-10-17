// /past-projects builder: saving checked rows from a search table. Covers the filtered select-all
// (it used to select every archive row), the in-flight state, retried detail requests, the outcome
// shown next to Save, and that the table being worked on does not jump when the saved results appear.
import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import type {Page} from '@playwright/test';
import {test, expect} from '../helpers/fixtures';
import {mockPastProjects, seedAuthenticatedSession} from '../helpers';
import type {ProjectTableRow} from '../../src/features/projects/api';

const SEMESTERS = ['2026 Spring', '2025 Fall', '2025 Spring', '2024 Fall', '2024 Spring', '2023 Fall'];

const archiveRows = (): ProjectTableRow[] =>
  Array.from({length: 30}, (_, index) => {
    const westernDigital = index < 12;
    return {
      id: westernDigital ? `wd-${index}` : `acme-${index}`,
      semester_label: SEMESTERS[index % SEMESTERS.length],
      class_code: 'CSE',
      team_number: `${300 + index}`,
      team_name: `Team ${index}`,
      project_title: westernDigital ? `WD Project ${index}` : `Acme Project ${index}`,
      organization: westernDigital ? 'Western Digital' : 'Acme Corp',
      industry: 'Technology',
      abstract: `Abstract ${index}`,
      student_names: `Student ${index}`,
      is_presenting: false,
      track: null,
      presentation_order: null,
    };
  });

// Detail requests take a realistic moment, and the first one for `flakyId` fails with a 503.
async function mockProjectDetails(page: Page, rows: ProjectTableRow[], flakyId?: string) {
  const requests: string[] = [];
  await page.route(/\/projects\/[^/]+\/(?:\?.*)?$/, async (route) => {
    const id = new URL(route.request().url()).pathname.split('/').at(-2) ?? '';
    const row = rows.find((project) => project.id === id);
    if (!row) return route.fallback();
    requests.push(id);
    await new Promise((settle) => setTimeout(settle, 150));
    if (id === flakyId && requests.filter((requested) => requested === id).length === 1) {
      return route.fulfill({status: 503, contentType: 'application/json', body: '{"detail":"Unavailable"}'});
    }
    return route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(row)});
  });
  return requests;
}

const searchTable = (page: Page) =>
  page.locator('section.search-table-card').filter({has: page.getByRole('heading', {level: 3, name: 'Search Table'})});

test('saves only the rows a filtered search shows, retrying a failed detail request', async ({page}) => {
  const rows = archiveRows();
  await seedAuthenticatedSession(page);
  await mockPastProjects(page, rows);
  const detailRequests = await mockProjectDetails(page, rows, 'wd-3');
  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});

  const table = searchTable(page);
  await table.getByRole('searchbox').fill('Western Digital');
  await expect(table.locator('.project-grid-count-value')).toHaveText('12 of 30');
  await table.locator('.project-grid-table-wrap').getByRole('checkbox', {name: 'Select all rows'}).check();
  await expect(table.getByText('12 selected', {exact: true}).first()).toBeVisible();
  await table.locator('.project-grid-table-wrap').getByRole('checkbox', {name: 'Select WD Project 0'}).uncheck();
  await expect(table.getByText('11 selected', {exact: true}).first()).toBeVisible();

  await table.getByRole('button', {name: 'Save Selected'}).first().click();
  await expect(table.getByRole('button', {name: 'Saving…'}).first()).toBeVisible();

  await expect(table.getByRole('status')).toHaveText('11 projects added to Saved Merged Results (11 in total).');
  const saved = page.locator('#past-projects-saved-results');
  await expect(saved.locator('.project-grid-count-value')).toHaveText('11 of 11');
  // Only the checked Western Digital rows were loaded, and the 503 was retried rather than failing the save.
  expect(new Set(detailRequests)).toEqual(new Set(rows.slice(1, 12).map((row) => row.id)));
  expect(detailRequests.filter((id) => id === 'wd-3')).toHaveLength(2);
  await expect(table.locator('.project-grid-table-wrap').getByRole('checkbox', {name: 'Select WD Project 0'})).not.toBeChecked();
  await expect(table.locator('.project-grid-table-wrap .project-grid-row-chip.is-saved').first()).toBeVisible();
});

// The e2e shell replaces /layout/styles.css with a structural stub; these checks need the real sheets.
const SEED_STYLESHEETS = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../src/apps/cms/migrations/data/stylesheets.json',
);

async function serveSeedStylesheets(page: Page) {
  const sheets = JSON.parse(readFileSync(SEED_STYLESHEETS, 'utf8')) as Array<{
    fields: {css: string; is_active: boolean; sort_order: number};
  }>;
  const css = sheets
    .filter((sheet) => sheet.fields.is_active)
    .sort((left, right) => left.fields.sort_order - right.fields.sort_order)
    .map((sheet) => sheet.fields.css)
    .join('\n');
  await page.route('**/layout/styles.css*', (route) => route.fulfill({status: 200, contentType: 'text/css', body: css}));
}

test('a disabled Save looks disabled and the first save does not move the table being worked on', async ({page}) => {
  const rows = archiveRows();
  await page.setViewportSize({width: 1440, height: 900});
  await serveSeedStylesheets(page);
  await seedAuthenticatedSession(page);
  await mockPastProjects(page, rows);
  await mockProjectDetails(page, rows);
  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});

  const table = searchTable(page);
  const save = table.getByRole('button', {name: 'Save Selected'}).first();
  await expect(save).toBeDisabled();
  const disabledLook = await save.evaluate((button) => {
    const style = getComputedStyle(button);
    return {background: style.backgroundColor, cursor: style.cursor};
  });
  expect(disabledLook.cursor).toBe('not-allowed');
  expect(disabledLook.background).not.toBe('rgb(15, 45, 82)');

  // From the top of the page the saved results card mounts below the browser's scroll anchor, which
  // used to push this table about 900px down.
  await page.evaluate(() => window.scrollTo(0, 0));
  await table.locator('.project-grid-table-wrap').getByRole('checkbox', {name: 'Select WD Project 0'}).check();
  const before = (await table.boundingBox())?.y ?? 0;
  await save.click();
  await expect(table.getByRole('status')).toHaveText('1 project added to Saved Merged Results (1 in total).');
  await expect(page.locator('#past-projects-saved-results')).toBeAttached();
  const after = (await table.boundingBox())?.y ?? 0;
  expect(Math.abs(after - before)).toBeLessThanOrEqual(2);
});

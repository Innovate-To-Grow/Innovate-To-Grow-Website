// /past-projects curations: the draft being built (its projects, name and note) outlives the tab, Save Curation
// is at the top of the saved results, the new curation's page says it was saved, and the member's saved
// curations are listed on Past Projects. Desktop engines only (untagged).
import type {Page} from '@playwright/test';
import type {PastProjectShare} from '../../src/features/projects/api';
import {mockPastProjects, pastProjectRows, seedAuthenticatedSession} from '../helpers';
import {expect, test} from '../helpers/fixtures';

const json = (body: unknown, status = 200) => ({status, contentType: 'application/json', body: JSON.stringify(body)});

async function openBuilder(page: Page, saved: PastProjectShare[]) {
  await seedAuthenticatedSession(page);
  await mockPastProjects(page, pastProjectRows());
  // Registered after the helpers, so these answer first.
  await page.route(/\/projects\/past-shares\/mine\/(?:\?.*)?$/, (route) =>
    route.fulfill(
      json(
        saved.map((share) => ({
          id: share.id,
          name: share.name,
          note: share.note,
          version: share.version,
          share_url: share.share_url,
          row_count: share.rows.length,
          created_at: share.created_at,
          updated_at: share.created_at,
        })),
      ),
    ),
  );
  await page.route(/\/projects\/past-shares\/(?:\?.*)?$/, async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const body = route.request().postDataJSON() as Pick<PastProjectShare, 'name' | 'note' | 'rows'>;
    const share: PastProjectShare = {
      id: 'share-new',
      name: body.name,
      note: body.note,
      rows: body.rows,
      details_text: '',
      version: 1,
      share_url: '/past-projects/share-new',
      can_edit: true,
      created_at: '2026-10-19T10:00:00Z',
    };
    saved.push(share);
    await route.fulfill(json(share, 201));
  });
  await page.route(/\/projects\/past-shares\/share-new\/(?:\?.*)?$/, (route) => route.fulfill(json(saved[0])));
  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});
}

test('a curation draft outlives the tab, and a saved curation is listed on Past Projects', async ({page, context}) => {
  const saved: PastProjectShare[] = [];
  const [project] = pastProjectRows();
  await openBuilder(page, saved);
  await expect(page.getByRole('heading', {level: 1, name: 'Past Projects'})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'My Curations'})).toHaveCount(0);

  await page
    .locator('section.search-table-card .project-grid-table-wrap')
    .getByRole('checkbox', {name: `Select ${project.project_title}`})
    .check();
  await page.getByRole('button', {name: 'Save Selected'}).first().click();
  const savedResults = page.locator('#past-projects-saved-results');
  await expect(savedResults.getByText('Not saved yet. This browser keeps the list until you save it.')).toBeVisible();
  await page.getByLabel('Curation name (optional)').fill('Water picks');
  await page.getByRole('textbox', {name: /Curation note/}).click();
  await page.keyboard.type('For the board meeting');

  // Close the tab and come back in a new one: sessionStorage is gone, the draft is not.
  const next = await context.newPage();
  await page.close();
  await openBuilder(next, saved);
  const restored = next.locator('#past-projects-saved-results');
  await expect(restored.getByText(project.project_title).first()).toBeVisible();
  await expect(next.getByLabel('Curation name (optional)')).toHaveValue('Water picks');
  await expect(next.getByRole('textbox', {name: /Curation note/})).toHaveText('For the board meeting');

  // The save at the top of the card, without scrolling to the form under the table.
  await restored.locator('.project-grid-card-header').getByRole('button', {name: 'Save Curation'}).click();
  await expect(next).toHaveURL(/\/past-projects\/share-new$/);
  const notice = next.locator('.past-projects-saved-notice');
  await expect(notice).toContainText('Curation saved.');
  expect(saved[0]).toMatchObject({name: 'Water picks', note: 'For the board meeting'});

  await notice.getByRole('link', {name: 'Past Projects'}).click();
  const curations = next.getByRole('region', {name: 'My Curations'});
  await expect(curations.getByRole('link', {name: 'Water picks'})).toHaveAttribute('href', '/past-projects/share-new');
  await expect(curations.getByText('1 project · updated Oct 19, 2026')).toBeVisible();
  // The saved draft is gone.
  await expect(next.locator('#past-projects-saved-results')).toHaveCount(0);
});

// /all-projects: the Past Projects builder over every project (/projects/all/), the active schedule's teams first and
// then the archive. A current team links to its own page, the server search reads its abstract, AI search ranks both
// lists, a curation may mix them, and the All Projects widget hands its draft over to this page. Desktop engines only
// (untagged).
import type {Page} from '@playwright/test';
import type {PastProjectShare, ProjectGridRow} from '../../src/features/projects/api';
import {
  aiSearchResponse,
  allProjectRows,
  cmsEmbedResponse,
  mockAiSearch,
  mockAllProjects,
  mockCmsEmbed,
  seedAuthenticatedSession,
} from '../helpers';
import {expect, test} from '../helpers/fixtures';

const json = (body: unknown, status = 200) => ({status, contentType: 'application/json', body: JSON.stringify(body)});

const searchTable = (page: Page) => page.locator('section.search-table-card').first();
const tableRows = (page: Page) => searchTable(page).locator('.project-grid-table-wrap');

async function addToCuration(page: Page, ...titles: string[]) {
  for (const title of titles) {
    await tableRows(page).getByRole('checkbox', {name: `Select ${title}`}).check();
  }
  await searchTable(page).getByRole('button', {name: 'Add to Curation'}).first().click();
  await expect(searchTable(page).getByRole('status')).toHaveText(
    `${titles.length} projects added to the curation draft (${titles.length} in total).`,
  );
}

test("lists this semester's teams before the archive, each linking to its own page", async ({page}) => {
  const rows = allProjectRows();
  const [listed, presenting, archived] = rows;
  const archiveRequests: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.endsWith('/projects/archive/')) archiveRequests.push(request.url());
  });
  await mockAllProjects(page, rows);
  await page.goto('/all-projects', {waitUntil: 'domcontentloaded'});

  await expect(page.getByRole('heading', {level: 1, name: 'All Projects'})).toBeVisible();
  await expect(page).toHaveTitle(/^All Projects/);
  await expect(page.locator('.past-projects-header .itg-page-meta')).toHaveText('4 projects since 2025');
  await expect(page.locator('.past-projects-header .itg-lead')).toContainText("this semester's teams and the archive");

  const table = tableRows(page);
  await expect(table.getByRole('link', {name: new RegExp(presenting.project_title)})).toHaveAttribute(
    'href',
    new RegExp(`/projects/${presenting.id}$`),
  );
  await expect(table.getByRole('link', {name: new RegExp(archived.project_title)})).toHaveAttribute(
    'href',
    new RegExp(`/past-projects/project/${archived.id}$`),
  );
  // A team the schedule only lists keeps the sheet's placeholder name, as stored.
  await expect(table.getByText(listed.team_name, {exact: true}).first()).toBeVisible();
  expect(archiveRequests).toEqual([]);
});

test("a search finds a current team by a word only in its abstract", async ({page}) => {
  const rows = allProjectRows();
  const presenting = rows[1];
  // "almond" is only in the presenting team's abstract, which the list's rows leave out.
  expect(presenting.abstract).toContain('almond');
  const searches: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.endsWith('/projects/all/') && url.searchParams.has('search')) {
      searches.push(url.searchParams.get('search') ?? '');
    }
  });
  await mockAllProjects(page, rows);
  await page.goto('/all-projects', {waitUntil: 'domcontentloaded'});

  const table = searchTable(page);
  await expect(table.locator('.project-grid-count')).toContainText('4 projects');
  await table.getByRole('searchbox').fill('almond');
  await expect(table.locator('.project-grid-count')).toContainText('1 of 4');
  await expect(table.getByText(presenting.project_title, {exact: true})).toBeVisible();
  expect(searches).toContain('almond');
});

test('AI search ranks every project, this semester\'s included', async ({page}) => {
  const rows = allProjectRows();
  const [, presenting, archived] = rows;
  await seedAuthenticatedSession(page);
  await mockAllProjects(page, rows);
  const {queries} = await mockAiSearch(page, {
    response: aiSearchResponse({query: 'soil sensors', results: [presenting, archived]}),
  });
  await page.goto('/all-projects', {waitUntil: 'domcontentloaded'});

  await page.getByRole('button', {name: '+ AI Search Table'}).click();
  const form = page.locator('.past-projects-ai-search');
  await form.getByPlaceholder('Ask about projects…').fill('soil sensors');
  await form.getByRole('button', {name: 'Search'}).click();

  await expect.poll(() => queries.length).toBe(1);
  expect(queries[0]).toMatchObject({query: 'soil sensors', scope: 'all'});
  const results = page
    .locator('section.search-table-card')
    .filter({has: page.getByRole('heading', {name: 'AI Search Table: soil sensors'})})
    .locator('.project-grid-table-wrap');
  await expect(results.getByRole('link', {name: new RegExp(presenting.project_title)})).toHaveAttribute(
    'href',
    new RegExp(`/projects/${presenting.id}$`),
  );
  await expect(results.getByRole('link', {name: new RegExp(archived.project_title)})).toHaveAttribute(
    'href',
    new RegExp(`/past-projects/project/${archived.id}$`),
  );
});

test('saves a curation of a current team and an archived one, named after All Projects', async ({page}) => {
  const rows = allProjectRows();
  const [, presenting, archived] = rows;
  await seedAuthenticatedSession(page);
  await mockAllProjects(page, rows);
  const posted: ProjectGridRow[][] = [];
  let saved: PastProjectShare | null = null;
  await page.route(/\/projects\/past-shares\/mine\/(?:\?.*)?$/, (route) => route.fulfill(json([])));
  await page.route(/\/projects\/past-shares\/(?:\?.*)?$/, async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    const body = route.request().postDataJSON() as Pick<PastProjectShare, 'name' | 'note' | 'rows'>;
    posted.push(body.rows);
    saved = {
      id: 'share-all',
      name: body.name,
      note: body.note,
      // Stored as the server rebuilds them: each names its catalog.
      rows: body.rows.map((row) => ({...row, catalog: row.catalog ?? 'archive'})),
      details_text: '',
      version: 1,
      share_url: '/past-projects/share-all',
      can_edit: true,
      created_at: '2026-10-31T10:00:00Z',
    };
    await route.fulfill(json(saved, 201));
  });
  const shareReads: string[] = [];
  await page.route(/\/projects\/past-shares\/share-all\/(?:\?.*)?$/, (route) => {
    shareReads.push(route.request().method());
    return route.fulfill(json(saved));
  });
  await page.goto('/all-projects', {waitUntil: 'domcontentloaded'});

  await addToCuration(page, presenting.project_title, archived.project_title);
  // Saved without a name, a curation holding this semester's team is a "Project Curation", not a past-project one.
  await expect(page.getByLabel('Curation name (optional)')).toHaveAttribute('placeholder', 'Project Curation');
  await page
    .locator('#past-projects-saved-results .project-grid-card-header')
    .getByRole('button', {name: 'Save Curation'})
    .click();

  await expect(page).toHaveURL(/\/past-projects\/share-all$/);
  // The POST names the current team by its CurrentProject id.
  expect(posted).toHaveLength(1);
  expect(new Set(posted[0].map((row) => row.id))).toEqual(new Set([presenting.id, archived.id]));
  const list = page.locator('section.project-grid-shared-list');
  await expect(list.locator('.itg-eyebrow')).toHaveText('Curation · All Projects');
  const notice = page.locator('.past-projects-saved-notice');
  await expect(notice).toContainText('Curation saved.');
  await expect(notice.getByRole('link', {name: 'All Projects'})).toHaveAttribute('href', '/all-projects');
  await expect(list.getByRole('link', {name: new RegExp(presenting.project_title)}).first()).toHaveAttribute(
    'href',
    new RegExp(`/projects/${presenting.id}$`),
  );
  await expect(list.getByRole('link', {name: new RegExp(archived.project_title)}).first()).toHaveAttribute(
    'href',
    new RegExp(`/past-projects/project/${archived.id}$`),
  );
  // The way to a list of one's own goes back to All Projects, which holds this semester's teams.
  const closing = page.locator('.past-projects-shared-closing');
  await expect(closing.getByRole('link', {name: 'Search all projects'})).toHaveAttribute('href', '/all-projects');
  // The save handed the curation over: the page never asked for it again.
  expect(shareReads).toEqual([]);

  // A reload restores the history entry with the curation as saved, which may be outdated: the page loads it.
  await page.reload({waitUntil: 'domcontentloaded'});
  await expect(list.locator('.itg-eyebrow')).toHaveText('Curation · All Projects');
  expect(shareReads).toEqual(['GET']);
});

test('the All Projects widget hands its draft over to /all-projects in a new tab', async ({page, context}) => {
  const rows = allProjectRows();
  const [, presenting, archived] = rows;
  // On the context, so the tab the widget opens is served too.
  await mockAllProjects(context, rows);
  await mockCmsEmbed(
    page,
    'all-projects-widget',
    cmsEmbedResponse({widget_type: 'app_route', app_route: '/all-projects', blocks: []}),
  );
  await page.goto('/_embed/all-projects-widget', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {level: 1, name: 'All Projects'})).toBeVisible();

  await addToCuration(page, presenting.project_title, archived.project_title);
  const handover = page
    .locator('#past-projects-saved-results')
    .getByRole('link', {name: /^Continue in All Projects/})
    .first();
  await expect(handover).toHaveAttribute('target', '_blank');
  const href = (await handover.getAttribute('href')) ?? '';
  const [path, ids] = href.split('#curation-draft=');
  expect(path).toBe('/all-projects');
  expect(new Set(ids.split(','))).toEqual(new Set([presenting.id, archived.id]));

  // A partner's frame keeps its storage apart from the site's: the full page starts without the widget's draft.
  await page.evaluate(() => localStorage.clear());
  const popup = context.waitForEvent('page');
  await handover.click();
  const tab = await popup;
  // The page takes the handover out of the address once it has added it.
  await tab.waitForURL(/\/all-projects$/);
  const draft = tab.locator('#past-projects-saved-results');
  await expect(draft.getByText(/^From the All Projects widget:/)).toHaveText(
    'From the All Projects widget: 2 projects added to the curation draft (2 in total).',
  );
  await expect(draft.getByRole('link', {name: new RegExp(presenting.project_title)}).first()).toHaveAttribute(
    'href',
    new RegExp(`/projects/${presenting.id}$`),
  );
  await tab.close();
});

test('"Section titles" hides the page header of an embedded All Projects page', async ({page}) => {
  const rows = allProjectRows();
  await mockAllProjects(page, rows);
  await mockCmsEmbed(
    page,
    'all-projects-no-titles',
    cmsEmbedResponse({
      widget_type: 'app_route',
      app_route: '/all-projects',
      blocks: [],
      hidden_sections: ['section_titles'],
    }),
  );
  await page.goto('/_embed/all-projects-no-titles', {waitUntil: 'domcontentloaded'});

  await expect(tableRows(page).getByRole('link', {name: new RegExp(rows[1].project_title)})).toBeVisible();
  await expect(page.getByRole('heading', {level: 1, name: 'All Projects'})).toBeHidden();
  // The meta line is there once the rows load, and goes with the rest of the header.
  const meta = page.locator('.past-projects-header .itg-page-meta');
  await expect(meta).toHaveText('4 projects since 2025');
  await expect(meta).toBeHidden();
  await expect(page.locator('.past-projects-header .itg-lead')).toBeHidden();
});

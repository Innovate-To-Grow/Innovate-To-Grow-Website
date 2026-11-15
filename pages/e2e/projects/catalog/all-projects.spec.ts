// /all-projects: the Past Projects builder over every project (/projects/all/), the active schedule's teams first and
// then the archive. A current team links to its own page, the server search reads its abstract, AI search ranks both
// lists, a curation may mix them, and the All Projects widget hands its draft over to this page. Desktop engines only
// (untagged).
import type {Page} from '@playwright/test';
import {
  aiSearchResponse,
  allProjectRows,
  mockAiSearch,
  mockAllProjects,
  seedAuthenticatedSession,
} from '../../helpers';
import {expect, test} from '../../helpers/fixtures';

const searchTable = (page: Page) => page.locator('section.search-table-card').first();
const tableRows = (page: Page) => searchTable(page).locator('.project-grid-table-wrap');

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

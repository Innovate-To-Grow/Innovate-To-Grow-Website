import {test, expect} from '../helpers/fixtures';
import {mockPastProjects, pastProjectRows} from '../helpers';

// The archive list loads without abstracts; a search also asks the server, which reads them, so a word that is only
// in an abstract finds its project, including from the Current Projects hand-off link (?value=).

test('@core a Past Projects search finds a project by a word in its abstract', async ({page}) => {
  const rows = pastProjectRows();
  await mockPastProjects(page, rows);
  const searches: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.endsWith('/projects/archive/') && url.searchParams.has('search')) {
      searches.push(url.searchParams.get('search') ?? '');
    }
  });
  // "residential" is only in the wind turbine's abstract.
  expect(rows[1].abstract).toContain('residential');

  await page.goto('/past-projects?value=residential', {waitUntil: 'domcontentloaded'});
  const table = page.locator('section.search-table-card').first();
  await expect(table.locator('.project-grid-count')).toContainText('1 of 2');
  await expect(table.getByText(rows[1].project_title, {exact: true})).toBeVisible();
  await expect(table.getByText(rows[0].project_title, {exact: true})).toHaveCount(0);

  await table.getByRole('searchbox').fill('irrigation schedules');
  await expect(table.getByText(rows[0].project_title, {exact: true})).toBeVisible();
  await expect(table.getByText(rows[1].project_title, {exact: true})).toHaveCount(0);
  expect(searches).toEqual(expect.arrayContaining(['residential', 'irrigation schedules']));
});

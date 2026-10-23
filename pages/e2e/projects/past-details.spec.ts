import {test, expect} from '../helpers/fixtures';
import {mockPastProjects, pastProjectRows} from '../helpers';

test('@core archive View shows abstract and students while preserving the individual project URL', async ({page}) => {
  const rows = pastProjectRows();
  await mockPastProjects(page, rows);
  const detailRequests: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.endsWith(`/projects/${rows[0].id}/`)) detailRequests.push(request.url());
  });
  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});
  const desktop = page.locator('.search-table-card .project-grid-table-wrap');
  const mobile = page.locator('.search-table-card .project-grid-mobile-cards');
  await expect(desktop.locator('tr.project-grid-row').filter({hasText: rows[0].project_title})).toHaveCount(1);
  // Cards replace the table at the projects CSS breakpoint (max-width: 768px). Read the layout from the
  // viewport: a mobile engine can briefly lay the page out wider while it applies the viewport meta tag.
  const isDesktop = (page.viewportSize()?.width ?? Number.POSITIVE_INFINITY) > 768;
  const row = isDesktop
    ? desktop.locator('tr.project-grid-row').filter({hasText: rows[0].project_title})
    : mobile.locator('.project-grid-mobile-card').filter({hasText: rows[0].project_title});
  await expect(row).toBeVisible();
  expect(detailRequests).toHaveLength(0);
  await row.getByRole('checkbox').check();
  await row.getByRole('button', {name: isDesktop ? 'Details' : 'Show details', exact: true}).click();
  const details = isDesktop ? row.locator('xpath=following-sibling::tr[1]') : row.locator('.project-grid-mobile-card-details');
  await expect(details.getByText(rows[0].abstract, {exact: false})).toBeVisible();
  await expect(details.getByText(rows[0].student_names, {exact: false})).toBeVisible();
  await expect(row.getByRole('checkbox')).toBeChecked();
  const projectLink = details.getByRole('link', {name: /Open the project page/});
  await expect(projectLink).toHaveAttribute('href', new URL(`/past-projects/project/${rows[0].id}`, page.url()).href);
  await expect(projectLink).toHaveAttribute('target', '_blank');
  await expect(details.getByRole('button', {name: 'Copy project link'})).toBeVisible();
  await expect.poll(() => detailRequests.length).toBe(1);

  await row.getByRole('button', {name: isDesktop ? 'Hide' : 'Hide details', exact: true}).click();
  await row.getByRole('button', {name: isDesktop ? 'Details' : 'Show details', exact: true}).click();
  await expect(details.getByText(rows[0].abstract, {exact: false})).toBeVisible();
  expect(detailRequests).toHaveLength(1);

  await page.goto(`/past-projects/project/${rows[0].id}`, {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: rows[0].project_title, exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Abstract', exact: true})).toBeVisible();
  // Team members are listed one per line.
  const members = page.locator('.project-detail-members li');
  await expect(members).toHaveText(rows[0].student_names.split(', '));
  await expect(page.getByRole('link', {name: /Back to Past Projects/}).first()).toHaveAttribute('href', '/past-projects');
  await expect(page.getByText(rows[1].project_title, {exact: true})).toHaveCount(0);
});

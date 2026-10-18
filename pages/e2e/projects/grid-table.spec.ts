// ProjectGridTable interactivity: column sorting, search, row expand/collapse,
// page size, pagination, and mobile card layout. Uses /current-projects as the
// canvas since it renders the grid with data from /event/schedule/.
import {test, expect} from '../helpers/fixtures';
import {mockSchedule, schedulePayload} from '../helpers';

// Helper: build a schedule payload with many projects for pagination tests.
function largePayload(projectCount = 15) {
  const projects = Array.from({length: projectCount}, (_, i) => ({
    id: `project-e2e-${i + 1}`,
    track: (i % 3) + 1,
    order: i + 1,
    year_semester: '2026 Spring',
    class_code: `CSE ${100 + i}`,
    team_number: `${i + 1}`,
    team_name: `Team ${String.fromCharCode(65 + (i % 26))}`,
    project_title: `Project Title ${i + 1}`,
    organization: `Org ${i + 1}`,
    industry: i % 2 === 0 ? 'Software' : 'Hardware',
    abstract: `Abstract for project ${i + 1}.`,
    student_names: `Student ${i + 1}`,
    is_presenting: true,
    tooltip: '',
  }));
  return schedulePayload({projects});
}

test('search input filters rows across all columns', async ({page}) => {
  await mockSchedule(page, largePayload(10));
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  const searchInput = page.locator('.project-grid-search-input');
  await expect(searchInput).toBeVisible();
  await searchInput.fill('Project Title 5');
  // After filtering, only matching rows should be visible.
  await expect(page.locator('.projects-page')).toContainText('Project Title 5');
});

test('row expand shows abstract and student names', async ({page}) => {
  await mockSchedule(page, schedulePayload());
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  // "Details" in the table, "Show details" in the phone list: whichever layout is showing.
  const toggle = page.locator('.project-grid-detail-button:visible').first();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('.projects-page')).toContainText('irrigation schedules');
});

test('"View All Details" and "Hide All Details" toggle', async ({page}) => {
  await mockSchedule(page, largePayload(3));
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  const viewAll = page.getByRole('button', {name: 'View All Details'});
  await viewAll.click();
  await expect(page.locator('.projects-page')).toContainText('Abstract for project 3.');
  const hideAll = page.getByRole('button', {name: 'Hide All Details'});
  await hideAll.click();
  await expect(page.getByRole('button', {name: 'View All Details'})).toBeVisible();
});

test('class and industry filters narrow the rows', async ({page}) => {
  await mockSchedule(page, largePayload(10));
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  await page.getByLabel('Industry').selectOption('Hardware');
  await expect(page.locator('.project-grid-count')).toContainText('5 of 10 projects match the filters');
  await page.getByLabel('Class').selectOption('CSE 101');
  await expect(page.locator('.project-grid-count')).toContainText('1 of 10 projects matches the filters');
  await expect(page.locator('.projects-page')).toContainText('Project Title 2');
});

test('a search with no results offers to clear it or search past projects', async ({page}) => {
  await mockSchedule(page, largePayload(3));
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  await page.locator('.project-grid-search-input').fill('hydroponics');
  await expect(page.getByRole('heading', {name: 'No projects match “hydroponics”'})).toBeVisible();
  await expect(page.getByRole('link', {name: 'Search Past Projects for “hydroponics”'})).toHaveAttribute(
    'href',
    '/past-projects?value=hydroponics',
  );
  await page.getByRole('button', {name: 'Clear search'}).click();
  await expect(page.locator('.project-grid-count')).toContainText('3 projects');
});

test('pagination advances to next page', async ({page}) => {
  // Build 15 projects to trigger pagination (default page size is 10).
  await mockSchedule(page, largePayload(15));
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  await page.getByRole('button', {name: 'Next', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Page 2', exact: true})).toHaveAttribute('aria-current', 'page');
  await expect(page.locator('.project-grid-count')).toContainText('showing 11–15');
  await expect(page.getByRole('heading', {name: 'Current Projects'})).toBeVisible();
});

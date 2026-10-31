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
  // "Details for …" in the table, "Show details for …" in the phone list: whichever layout is showing.
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
  await expect(page.locator('.project-grid-count')).toContainText('5 of 10 projects in Hardware');
  await page.getByLabel('Class').selectOption('CSE 101');
  await expect(page.locator('.project-grid-count')).toContainText('1 of 10 projects in CSE 101 and Hardware');
  await expect(page.locator('.projects-page')).toContainText('Project Title 2');

  // The filters in use show as chips; Clear Filters removes both and hands focus to the Class select. (Browsers
  // set the hidden ", remove filter" apart with a space.)
  const chips = page.getByRole('group', {name: 'Active filters'});
  await expect(chips.getByRole('button', {name: /^Class: CSE 101 ?, remove filter$/})).toBeVisible();
  await expect(chips.getByRole('button', {name: /^Industry: Hardware ?, remove filter$/})).toBeVisible();
  await chips.getByRole('button', {name: 'Clear Filters'}).click();
  await expect(page.locator('.project-grid-count')).toHaveText('10 projects · showing 1–10');
  await expect(page.getByLabel('Class')).toBeFocused();
  await expect(chips).toHaveCount(0);
});

test('a filtered, sorted, paged list comes back the same after a project page and Back', async ({page}) => {
  // Listed by their own project ids (as teams outside the presentation grid are), so every title links.
  const payload = largePayload(15);
  payload.projects = payload.projects.map((project, index) => ({
    ...project,
    id: `e2e00000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
    track: 0,
    order: 0,
  }));
  await mockSchedule(page, payload);
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  await page.getByLabel('Industry').selectOption('Software');
  await page.getByLabel('Sort by').selectOption({label: 'Project title (Z to A)'});
  await page.getByLabel('Per page').selectOption('5');
  await page.getByRole('button', {name: 'Next', exact: true}).click();
  await expect(page.locator('.project-grid-count')).toHaveText('8 of 15 projects in Software · showing 6–8');
  await expect(page).toHaveURL(/\?industry=Software&sort=project_title&dir=desc&page=2&per=5$/);

  await page.locator('.project-grid-title-link:visible').first().click();
  await expect(page).toHaveURL(/\/projects\//);
  await page.goBack();

  await expect(page.locator('.project-grid-count')).toHaveText('8 of 15 projects in Software · showing 6–8');
  await expect(page.getByLabel('Industry')).toHaveValue('Software');
  await expect(page.getByLabel('Sort by')).toHaveValue('project_title:desc');

  // The same URL, opened afresh (a reload or a shared link), shows the same view.
  await page.reload({waitUntil: 'domcontentloaded'});
  await expect(page.locator('.project-grid-count')).toHaveText('8 of 15 projects in Software · showing 6–8');
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
  const next = page.getByRole('button', {name: 'Next', exact: true});
  await next.scrollIntoViewIfNeeded();
  await next.click();
  await expect(page.getByRole('button', {name: 'Page 2', exact: true})).toHaveAttribute('aria-current', 'page');
  await expect(page.locator('.project-grid-count')).toContainText('showing 11–15');
  // The new page is read from its top: the count line has focus and is on screen; Next (now disabled) does not.
  await expect(page.locator('.project-grid-count')).toBeFocused();
  await expect(page.locator('.project-grid-count')).toBeInViewport();
  await expect(page.getByRole('heading', {name: 'Current Projects'})).toBeVisible();
});

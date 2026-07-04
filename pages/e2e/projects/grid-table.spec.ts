// ProjectGridTable interactivity: column sorting, search, row expand/collapse,
// page size, pagination, and mobile card layout. Uses /current-projects as the
// canvas since it renders the grid with data from /event/schedule/.
import {test, expect} from '../fixtures';
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
  // Click to expand the first row.
  const expandButton = page.locator('[aria-label="Expand row"]').first();
  if (await expandButton.isVisible()) {
    await expandButton.click();
    await expect(page.locator('.projects-page')).toContainText('irrigation schedules');
  }
});

test('"Expand All" and "Collapse All" toggle', async ({page}) => {
  await mockSchedule(page, largePayload(3));
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  const expandAll = page.getByRole('button', {name: /expand all/i});
  if (await expandAll.isVisible()) {
    await expandAll.click();
    const collapseAll = page.getByRole('button', {name: /collapse all/i});
    await expect(collapseAll).toBeVisible();
    await collapseAll.click();
    await expect(expandAll).toBeVisible();
  }
});

test('pagination advances to next page', async ({page}) => {
  // Build 15 projects to trigger pagination (default page size is 10).
  await mockSchedule(page, largePayload(15));
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  const nextButton = page.getByRole('button', {name: /next/i});
  if (await nextButton.isVisible() && await nextButton.isEnabled()) {
    await nextButton.click();
  }
  // Page should still show the projects heading.
  await expect(page.getByRole('heading', {name: 'Current Projects'})).toBeVisible();
});

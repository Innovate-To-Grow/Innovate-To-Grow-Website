// Current projects + presenting teams (from /event/schedule/), past projects
// (/projects/past-all/), and the single project detail (/projects/:id/).
import {test, expect} from './fixtures';
import {
  mockPastProjects,
  mockProjectDetail,
  mockSchedule,
  pastProjectRows,
  projectDetail,
  schedulePayload,
} from './helpers';

test('current projects grid renders rows', {tag: '@core'}, async ({page}) => {
  await mockSchedule(page, schedulePayload());
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Current Projects'})).toBeVisible();
  // The grid renders into both a desktop table and mobile cards; assert on the
  // page container's text so it holds on every viewport.
  await expect(page.locator('.projects-page')).toContainText('Adaptive Irrigation Dashboard');
});

test('current projects empty state', async ({page}) => {
  await mockSchedule(page, schedulePayload({projects: []}));
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.projects-page')).toContainText('No current projects are available yet.');
});

test('presenting teams grid renders', async ({page}) => {
  await mockSchedule(page, schedulePayload());
  await page.goto('/presenting-teams', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Presenting Teams'})).toBeVisible();
});

test('past projects page renders', async ({page}) => {
  await mockPastProjects(page, pastProjectRows());
  await page.goto('/past-projects', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Past Projects'})).toBeVisible();
});

test('project detail renders title and abstract', {tag: '@core'}, async ({page}) => {
  await mockProjectDetail(page, projectDetail());
  await page.goto('/projects/project-e2e-1', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Adaptive Irrigation Dashboard'})).toBeVisible();
  await expect(page.locator('.project-detail-abstract')).toContainText('irrigation schedules');
});

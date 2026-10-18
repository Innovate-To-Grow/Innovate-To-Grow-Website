// /projects/:id and /past-projects/project/:id: project detail page. /projects/:id looks in the current
// schedule first (see current-detail.spec.ts); the schedule mocked here does not have these archive ids.
import {test, expect} from '../helpers/fixtures';
import {mockProjectDetail, mockSchedule, projectDetail, schedulePayload} from '../helpers';

test('project detail renders title and abstract', {tag: '@core'}, async ({page}) => {
  await mockSchedule(page, schedulePayload());
  await mockProjectDetail(page, projectDetail());
  await page.goto('/projects/project-e2e-1', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Adaptive Irrigation Dashboard'})).toBeVisible();
  await expect(page.locator('.project-detail-abstract')).toContainText('irrigation schedules');
});

test('project detail shows error state on 404', async ({page}) => {
  await mockSchedule(page, schedulePayload());
  await mockProjectDetail(page, projectDetail({id: 'missing'}), {status: 404});
  await page.goto('/projects/missing', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.projects-error')).toBeVisible();
  await expect(page.getByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeVisible();
});

test('project detail accessible from past-projects route', async ({page}) => {
  await mockProjectDetail(page, projectDetail());
  await page.goto('/past-projects/project/project-e2e-1', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Adaptive Irrigation Dashboard'})).toBeVisible();
});

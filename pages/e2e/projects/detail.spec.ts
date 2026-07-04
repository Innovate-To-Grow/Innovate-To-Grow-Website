// /projects/:id and /past-projects/project/:id: project detail page.
import {test, expect} from '../fixtures';
import {mockProjectDetail, projectDetail} from '../helpers';

test('project detail renders title and abstract', {tag: '@core'}, async ({page}) => {
  await mockProjectDetail(page, projectDetail());
  await page.goto('/projects/project-e2e-1', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Adaptive Irrigation Dashboard'})).toBeVisible();
  await expect(page.locator('.project-detail-abstract')).toContainText('irrigation schedules');
});

test('project detail shows error state on 404', async ({page}) => {
  await mockProjectDetail(page, projectDetail({id: 'missing'}), {status: 404});
  await page.goto('/projects/missing', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.projects-error')).toBeVisible();
});

test('project detail accessible from past-projects route', async ({page}) => {
  await mockProjectDetail(page, projectDetail());
  await page.goto('/past-projects/project/project-e2e-1', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Adaptive Irrigation Dashboard'})).toBeVisible();
});

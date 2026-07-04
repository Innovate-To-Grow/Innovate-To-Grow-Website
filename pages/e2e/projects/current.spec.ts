// /current-projects: project grid populated from /event/schedule/.
import {test, expect} from '../fixtures';
import {mockSchedule, schedulePayload} from '../helpers';

test('current projects grid renders rows', {tag: '@core'}, async ({page}) => {
  await mockSchedule(page, schedulePayload());
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Current Projects'})).toBeVisible();
  await expect(page.locator('.projects-page')).toContainText('Adaptive Irrigation Dashboard');
});

test('current projects empty state', async ({page}) => {
  await mockSchedule(page, schedulePayload({projects: []}));
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.projects-page')).toContainText('No current projects are available yet.');
});

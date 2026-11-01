// /current-projects: project grid populated from /event/schedule/.
import {test, expect} from '../helpers/fixtures';
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
  await expect(page.getByRole('heading', {level: 2, name: 'No current projects yet'})).toBeVisible();
  await expect(page.locator('.projects-page')).toContainText(
    "This semester's projects appear here once the schedule is published. Older projects are in Past Projects.",
  );
  await expect(page.getByRole('link', {name: 'Search Past Projects'})).toHaveAttribute('href', '/past-projects');
});

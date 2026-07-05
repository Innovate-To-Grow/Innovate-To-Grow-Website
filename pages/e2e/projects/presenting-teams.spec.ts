// /presenting-teams: filtered project grid showing only presenting teams.
import {test, expect} from '../fixtures';
import {mockSchedule, schedulePayload} from '../helpers';

test('presenting teams grid renders', async ({page}) => {
  await mockSchedule(page, schedulePayload());
  await page.goto('/presenting-teams', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Presenting Teams'})).toBeVisible();
  await expect(page.locator('.projects-page')).toContainText('Adaptive Irrigation Dashboard');
});

test('presenting teams empty state when no teams are presenting', async ({page}) => {
  const empty = schedulePayload({
    projects: [
      {
        id: 'project-e2e-1',
        track: 1,
        order: 3,
        year_semester: '2026 Spring',
        class_code: 'CSE 120',
        team_number: '7',
        team_name: 'Team Helix',
        project_title: 'Adaptive Irrigation Dashboard',
        organization: 'Acme Corp',
        industry: 'Agriculture',
        abstract: 'A dashboard.',
        student_names: 'Ada Lovelace',
        is_presenting: false,
        tooltip: '',
      },
    ],
  });
  await mockSchedule(page, empty);
  await page.goto('/presenting-teams', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.projects-page')).toContainText('No presenting teams are available yet.');
});

// /schedule: full interactive event schedule with winners, expo, presentation
// tracks (desktop table + mobile cards), and embedded project grid search.
import {test, expect} from '../helpers/fixtures';
import {mockSchedule, schedulePayload} from '../helpers';

test('empty schedule without sections or projects', async ({page}) => {
  const empty = schedulePayload({
    show_winners: false,
    expo: {title: 'Expo', location: '', items: []},
    sections: [],
    awards: {title: 'Awards', location: '', items: []},
    projects: [],
  });
  await mockSchedule(page, empty);
  await page.goto('/schedule', {waitUntil: 'domcontentloaded'});
  // The loaded h1 is the event name ("Event Schedule" is only the
  // loading/error-state heading); an empty payload must still render it.
  await expect(page.getByRole('heading', {name: 'E2E Showcase'})).toBeVisible();
});

test('schedule with multiple presentation tracks and sections', async ({page}) => {
  const payload = schedulePayload({
    sections: [
      {
        title: 'CSE',
        location: 'Room 101',
        code: 'CSE',
        tracks: [
          {
            id: 'track-1',
            track_number: 1,
            topic: 'AI/ML',
            room: 'Room 101',
            winner: '',
            slots: [],
          },
          {
            id: 'track-2',
            track_number: 2,
            topic: 'Systems',
            room: 'Room 101',
            winner: '',
            slots: [],
          },
        ],
      },
      {
        title: 'CAP',
        location: 'Room 102',
        code: 'CAP',
        tracks: [
          {
            id: 'track-3',
            track_number: 1,
            topic: 'Design',
            room: 'Room 102',
            winner: '',
            slots: [],
          },
        ],
      },
    ],
  });
  await mockSchedule(page, payload);
  await page.goto('/schedule', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.schedule-presentation-block')).toHaveCount(2);
  await expect(page.locator('.schedule-page')).toContainText('CSE');
  await expect(page.locator('.schedule-page')).toContainText('CAP');
});

test('schedule with awards section', async ({page}) => {
  const payload = schedulePayload({
    awards: {
      title: 'Awards Ceremony',
      location: 'Main Stage',
      items: [
        {time: '8:00 PM', title: 'Grand Prize Announcement'},
        {time: '8:15 PM', title: 'Closing Remarks'},
      ],
    },
  });
  await mockSchedule(page, payload);
  await page.goto('/schedule', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.schedule-page')).toContainText('Awards Ceremony');
  await expect(page.locator('.schedule-page')).toContainText('Grand Prize Announcement');
});

test('loading state before schedule resolves', async ({page}) => {
  // Delay the schedule response so the loading state is visible.
  await page.route(/\/event\/schedule\//, async (route) => {
    await new Promise((r) => setTimeout(r, 500));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(schedulePayload()),
    });
  });
  await page.goto('/schedule', {waitUntil: 'domcontentloaded'});
  // The loading spinner or state text should render momentarily.
  await expect(page.locator('.schedule-page-state')).toBeVisible();
});

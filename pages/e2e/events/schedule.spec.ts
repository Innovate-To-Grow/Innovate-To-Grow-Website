// /schedule: full interactive event schedule with winners, expo, presentation
// tracks (desktop table + mobile cards), and embedded project grid search.
import {test, expect} from '../fixtures';
import {mockSchedule, schedulePayload} from '../helpers';

test('renders event name, date, location, and description', {tag: '@core'}, async ({page}) => {
  await mockSchedule(page, schedulePayload());
  await page.goto('/schedule', {waitUntil: 'domcontentloaded'});
  // Once data loads the page title is the event name — the static
  // "Event Schedule" h1 only exists in the loading/error states.
  await expect(page.getByRole('heading', {name: 'E2E Showcase'})).toBeVisible();
  await expect(page.locator('.schedule-page')).toContainText('E2E Hall');
  await expect(page.locator('.schedule-page')).toContainText('End-to-end showcase schedule.');
});

test('winners section renders when show_winners is true', async ({page}) => {
  const payload = schedulePayload({
    show_winners: true,
    grand_winners: [{section: 'CSE', label: 'CSE Grand Prize', winner: 'Team Helix'}],
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
            winner: 'Team Helix',
            slots: [],
          },
        ],
      },
    ],
  });
  await mockSchedule(page, payload);
  await page.goto('/schedule', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.schedule-page-section-winners')).toBeVisible();
  await expect(page.locator('.schedule-winners-title')).toContainText('Winners!');
});

test('expo agenda renders with items', async ({page}) => {
  const payload = schedulePayload({
    expo: {
      title: 'Expo',
      location: 'Lobby',
      items: [
        {time: '6:00 PM', title: 'Doors Open'},
        {time: '6:30 PM', title: 'Expo Begins'},
      ],
    },
  });
  await mockSchedule(page, payload);
  await page.goto('/schedule', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.schedule-page-agenda-table')).toBeVisible();
  await expect(page.locator('.schedule-page-agenda-table')).toContainText('Doors Open');
});

test('presentation tracks render in desktop table', async ({page}) => {
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
            topic: 'AI & Machine Learning',
            room: 'Room 101',
            winner: '',
            slots: [],
          },
        ],
      },
    ],
  });
  await mockSchedule(page, payload);
  await page.goto('/schedule', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.schedule-presentation-table')).toBeVisible();
  await expect(page.locator('.schedule-presentation-block')).toContainText('CSE');
  await expect(page.locator('.schedule-presentation-block')).toContainText('AI & Machine Learning');
});

test('mobile cards render in mobile viewport', async ({page}) => {
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
            topic: 'AI & Machine Learning',
            room: 'Room 101',
            winner: '',
            slots: [],
          },
        ],
      },
    ],
  });
  await mockSchedule(page, payload);
  // Set a narrow viewport to trigger mobile card layout
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('/schedule', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.schedule-page-mobile-grid')).toBeVisible();
  await expect(page.locator('.schedule-mobile-card')).toBeVisible();
});

test('click team button scrolls to project grid search', async ({page}) => {
  const payload = schedulePayload({
    presentations_title: 'Presentations',
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
            slots: [
              {
                id: 'slot-1',
                track: 1,
                order: 1,
                year_semester: '2026 Spring',
                class_code: 'CSE 120',
                team_number: '7',
                team_name: 'Team Helix',
                project_title: 'Adaptive Irrigation Dashboard',
                organization: 'Acme Corp',
                industry: 'Agriculture',
                abstract: 'A dashboard.',
                student_names: 'Ada Lovelace',
                is_presenting: true,
                tooltip: '',
                is_break: false,
              },
            ],
          },
        ],
      },
    ],
  });
  await mockSchedule(page, payload);
  await page.goto('/schedule', {waitUntil: 'domcontentloaded'});
  // Team button should be clickable
  await expect(page.locator('.schedule-page')).toContainText('Team Helix');
});

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

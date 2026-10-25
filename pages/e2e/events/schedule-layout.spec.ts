// /schedule with the site's real CSS: the presentation grids fit the full-width
// content column, schedule text meets WCAG AA contrast, long winner
// names stay inside their cards, and phone team buttons are 44px touch targets.
import AxeBuilder from '@axe-core/playwright';
import type {Page} from '@playwright/test';

import type {ScheduleSection, ScheduleSlot, ScheduleTrack} from '../../src/features/events/api';
import {mockSchedule, schedulePayload} from '../helpers';
import {test, expect} from '../helpers/fixtures';

const LONG_ORGANIZATIONS = [
  'University of California Agriculture and Natural Resources (UC ANR)',
  'Lawrence Livermore National Laboratory',
  // Production data really has a no-break space here.
  'UC Merced Sustainability Office',
  'OrthoSpine Advance Health, Inc.',
  'Woodpecker Microsystems and MIUGSA',
];

function slot(trackNumber: number, order: number, overrides: Partial<ScheduleSlot> = {}): ScheduleSlot {
  const team = String(trackNumber * 100 + order);
  return {
    id: `slot-${trackNumber}-${order}`,
    order,
    is_break: false,
    display_text: team,
    team_number: team,
    team_name: `Team ${team}`,
    project_title: `Project ${team}`,
    organization: LONG_ORGANIZATIONS[(trackNumber + order) % LONG_ORGANIZATIONS.length],
    industry: '',
    abstract: '',
    student_names: '',
    tooltip: '',
    project_id: null,
    ...overrides,
  };
}

function track(trackNumber: number, topic: string, winner: string): ScheduleTrack {
  return {
    id: `track-${trackNumber}`,
    track_number: trackNumber,
    label: `Track ${trackNumber}`,
    room: `Glacier ${100 + trackNumber * 5}`,
    zoom_link: '',
    topic,
    winner,
    display_order: trackNumber,
    slots: [1, 2, 3, 4].map((order) => (order === 3 ? slot(trackNumber, order, {is_break: true}) : slot(trackNumber, order))),
  };
}

function section(code: string, label: string, firstTrack: number, topics: string[], winners: string[]): ScheduleSection {
  return {
    id: `section-${code}`,
    code,
    label,
    display_order: firstTrack,
    start_time: '13:00',
    slot_minutes: 20,
    accent_color: '',
    max_order: 4,
    tracks: topics.map((topic, index) => track(firstTrack + index, topic, winners[index] ?? '')),
  };
}

// Five tracks per class, like the production schedule: gold (CAP) and navy (CSE) families.
const CAP = section(
  'CAP',
  'Engineering Capstone',
  1,
  ['Gases', 'Fluids', 'FoodTech', 'AgTech', 'BioTech'],
  ['CAP-122: Smart Oxygen Delivery System', 'CAP-112: Team Shell', 'CAP-105: Mo Mandarins', 'CAP-110: Water Stressed', 'CAP-124: Aortic Simulation'],
);
const CSE = section(
  'CSE',
  'Software Engineering Capstone',
  6,
  ['Ada Lovelace', 'Grace Hopper', 'Hedy Lamarr', 'Margaret Hamilton', 'Katherine Johnson'],
  ['CSE-317: PhishBusters', 'CSE-312: SMART-BART', 'CSE-324: 24 Carrot', 'CSE-313: BART Simpson', 'CSE-320: SweepShield'],
);

function payload(sections: ScheduleSection[] = [CAP, CSE]) {
  return schedulePayload({
    show_winners: true,
    grand_winners: [
      {section: 'CAP', winner: 'CAP-104: MillGuard Systems'},
      {section: 'CSE', winner: 'CSE-330: The Kaleidoscope'},
    ],
    sections,
  });
}

// /schedule belongs to the Events menu section; the shell still shows no section sidebar.
async function mockEventsSection(page: Page) {
  const item = (title: string, url: string) => ({type: 'app', title, icon: '', open_in_new_tab: false, url, children: []});
  await page.route('**/layout/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        menus: [{
          id: 'menu-e2e',
          name: 'main',
          display_name: 'Main',
          items: [{
            ...item('Events', '/event'),
            children: [item('Event Info', '/event'), item('Schedule', '/schedule'), item('Past Events', '/past-events')],
          }],
        }],
        footer: null,
        homepage_route: '/',
      }),
    }),
  );
}

async function openSchedule(page: Page, width: number, sections?: ScheduleSection[]) {
  await page.setViewportSize({width, height: 900});
  await mockEventsSection(page);
  await mockSchedule(page, payload(sections));
  await page.goto('/schedule', {waitUntil: 'networkidle'});
  await expect(page.getByRole('heading', {name: 'E2E Showcase', level: 1})).toBeVisible();
}

// The schedule spans the whole content column at every width (1170px at 1440).
for (const width of [1440, 1024, 993, 768, 721]) {
  test(`five-track presentation grids fit the ${width}px layout without clipping a track`, async ({page}) => {
    await openSchedule(page, width);
    await expect(page.locator('.section-nav, .section-nav-select')).toHaveCount(0);
    const column = (await page.locator('.app-layout-main').boundingBox())!;
    expect((await page.locator('.schedule-page').boundingBox())!.width).toBeGreaterThanOrEqual(column.width - 1);
    if (width === 1440) expect(column.width).toBe(1170);

    const wraps = page.locator('.schedule-page-table-wrap');
    await expect(wraps).toHaveCount(2);
    for (const wrap of await wraps.all()) {
      const fit = await wrap.evaluate((element) => {
        const box = element.getBoundingClientRect();
        const tracks = [...element.querySelectorAll('thead tr:nth-child(2) th')].map((th) => th.getBoundingClientRect().right);
        return {scroll: element.scrollWidth, client: element.clientWidth, right: box.right, lastTrackRight: Math.max(...tracks)};
      });
      expect(fit.scroll).toBeLessThanOrEqual(fit.client + 1);
      expect(fit.lastTrackRight).toBeLessThanOrEqual(fit.right + 1);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}

test('a class with more tracks than fit scrolls inside its grid, not the page', async ({page}) => {
  const wide = section('CSE', 'Software Engineering Capstone', 6, ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'], []);
  await openSchedule(page, 1024, [wide]);

  const wrap = page.locator('.schedule-page-table-wrap');
  const sizes = await wrap.evaluate((element) => ({scroll: element.scrollWidth, client: element.clientWidth}));
  expect(sizes.scroll).toBeGreaterThan(sizes.client);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1024);
});

test('long winner names wrap inside their track cards', async ({page}) => {
  await openSchedule(page, 1024);

  const escaping = await page.locator('.schedule-winner-card').evaluateAll((cards) =>
    cards.flatMap((card) => {
      const cardRight = card.getBoundingClientRect().right;
      return [...card.querySelectorAll('.schedule-winner-topic, .schedule-winner-name')]
        .filter((text) => {
          const range = document.createRange();
          range.selectNodeContents(text);
          return range.getBoundingClientRect().right > cardRight - parseFloat(getComputedStyle(text).paddingRight) + 0.5;
        })
        .map((text) => text.textContent);
    }),
  );
  expect(escaping).toEqual([]);
});

for (const width of [1440, 390]) {
  test(`schedule text meets WCAG AA contrast at ${width}px`, async ({page}) => {
    await openSchedule(page, width);
    await expect(page.locator('.schedule-grand-winner-line.is-cap')).toBeVisible();

    const results = await new AxeBuilder({page}).include('.schedule-page').withRules(['color-contrast']).analyze();
    expect(results.violations).toEqual([]);
  });
}

test('phone team buttons are 44px touch targets', async ({page}) => {
  await openSchedule(page, 390);

  const teams = page.locator('.schedule-mobile-team');
  expect(await teams.count()).toBeGreaterThan(0);
  const boxes = await teams.evaluateAll((buttons) => buttons.map((button) => button.getBoundingClientRect()));
  for (const box of boxes) {
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(box.width).toBeGreaterThanOrEqual(44);
  }
});

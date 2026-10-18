// Current Projects / Presenting Teams -> /projects/:id. The schedule payload has the production shape: a
// presenting team's row id is its schedule SLOT id, the slot's project_id is the event CurrentProject id the
// list links to, and teams that are not presenting are listed at track 0 by their CurrentProject id. None of
// those ids is an archive Project id, so /projects/<id>/ answers 404 for all of them, as in production.
import type {Page} from '@playwright/test';
import type {EventSchedulePayload} from '../../src/features/events/api';
import {test, expect} from '../helpers/fixtures';
import {mockProjectDetail, mockSchedule, projectDetail, schedulePayload} from '../helpers';

const HVAC_SLOT_ID = '0ef6b199-6fb0-4d9d-9e95-11b5d6f0006c';
const HVAC_PROJECT_ID = '2280fa08-f914-45fe-8a62-905b2d68e0df';
const WING_PROJECT_ID = 'cbea890e-224f-4fb8-b358-1e1f5ee288eb';
const ARCHIVE_PROJECT_ID = '5970763b-cf7c-40d6-a87c-96916e0ea695';

const HVAC = {
  team_number: '101',
  team_name: 'HVAC Regulators',
  project_title: 'ASHRAE HVAC Design Calculations',
  organization: 'ASHRAE - Sierra Delta',
  industry: 'Energy',
  abstract: 'This project aimed to design a complete HVAC system for a multi-use university building.',
  student_names: 'Brian Arroyo, Joel Gonzalez, Kyle On, Manuel Cruz Cavero',
  tooltip: 'Team: HVAC Regulators  -  Project: ASHRAE HVAC Design Calculations',
};

function currentSchedule(): EventSchedulePayload {
  return schedulePayload({
    sections: [
      {
        id: '57f55878-a96d-4b7d-b59c-dfabc2fdc638',
        code: 'CAP',
        label: 'Engineering Capstone',
        display_order: 0,
        start_time: '1:00',
        slot_minutes: 30,
        accent_color: '#002856',
        max_order: 1,
        tracks: [
          {
            id: '27af1c24-9f01-46f6-8eda-1a7e2b0564bf',
            track_number: 1,
            label: 'Track 1',
            room: 'Glacier 165',
            zoom_link: '',
            topic: 'Gases',
            winner: '',
            display_order: 0,
            slots: [
              {...HVAC, id: HVAC_SLOT_ID, order: 1, is_break: false, display_text: '101', project_id: HVAC_PROJECT_ID},
            ],
          },
        ],
      },
    ],
    projects: [
      {
        ...HVAC,
        id: HVAC_SLOT_ID,
        track: 1,
        order: 1,
        year_semester: '2026-1 Spring',
        class_code: 'CAP',
        is_presenting: true,
      },
      {
        id: WING_PROJECT_ID,
        track: 0,
        order: 0,
        year_semester: '',
        class_code: 'CAP',
        team_number: '201',
        team_name: 'CAP-201',
        project_title: 'Distributed-Flapping Wing with Glide-Lock Mechanism',
        organization: 'UCM Aerospace',
        industry: 'AeroSpace',
        abstract: 'Abstract-201',
        student_names: '',
        is_presenting: false,
        tooltip: '',
      },
    ],
  });
}

/** The archive detail endpoint knows none of the schedule's ids. */
async function mockArchiveWithout(page: Page): Promise<void> {
  await page.route(
    (url) => /\/projects\/[^/]+\/$/.test(url.pathname) && !url.pathname.includes('/past-'),
    (route) => route.fulfill({status: 404, contentType: 'application/json', body: '{"detail":"Not found."}'}),
  );
}

// Titles render in the desktop table and in the phone cards; only the layout for this viewport is visible.
const visibleLink = (page: Page, name: string) => page.getByRole('link', {name, exact: true}).filter({visible: true});

test('a Current Projects title opens its populated project page', {tag: '@core'}, async ({page}) => {
  await mockArchiveWithout(page);
  await mockSchedule(page, currentSchedule());
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});

  const title = visibleLink(page, 'ASHRAE HVAC Design Calculations');
  await expect(title).toHaveAttribute('href', `/projects/${HVAC_PROJECT_ID}`);
  await title.click();

  await expect(page).toHaveURL(new RegExp(`/projects/${HVAC_PROJECT_ID}$`));
  await expect(page.getByRole('heading', {level: 1, name: 'ASHRAE HVAC Design Calculations'})).toBeVisible();
  await expect(page.getByText('Engineering Capstone · Spring 2026')).toBeVisible();
  await expect(page.locator('.project-detail-abstract')).toContainText('complete HVAC system');
  await expect(page.getByRole('heading', {level: 2, name: 'Team members'})).toBeVisible();
  await expect(page.getByRole('link', {name: /Back to Current Projects/}).first()).toHaveAttribute(
    'href',
    '/current-projects',
  );
  await expect(page.getByText("We couldn't find this project")).toHaveCount(0);
});

test('a team that is not presenting opens its project page', async ({page}) => {
  await mockArchiveWithout(page);
  await mockSchedule(page, currentSchedule());
  await page.goto('/current-projects', {waitUntil: 'domcontentloaded'});

  await visibleLink(page, 'Distributed-Flapping Wing with Glide-Lock Mechanism').click();

  await expect(page).toHaveURL(new RegExp(`/projects/${WING_PROJECT_ID}$`));
  await expect(
    page.getByRole('heading', {level: 1, name: 'Distributed-Flapping Wing with Glide-Lock Mechanism'}),
  ).toBeVisible();
  await expect(page.locator('.project-detail-abstract')).toHaveText('Abstract-201');
});

test('a Presenting Teams title opens its populated project page', async ({page}) => {
  await mockArchiveWithout(page);
  await mockSchedule(page, currentSchedule());
  await page.goto('/presenting-teams', {waitUntil: 'domcontentloaded'});

  await visibleLink(page, 'ASHRAE HVAC Design Calculations').click();

  await expect(page.getByRole('heading', {level: 1, name: 'ASHRAE HVAC Design Calculations'})).toBeVisible();
  await expect(page.locator('.project-detail-abstract')).toContainText('complete HVAC system');
});

test('an archive project id on /projects/:id still opens the archive project', async ({page}) => {
  await mockSchedule(page, currentSchedule());
  await mockProjectDetail(page, projectDetail({id: ARCHIVE_PROJECT_ID, project_title: 'ASHRAE HVAC (archive)'}));
  await page.goto(`/projects/${ARCHIVE_PROJECT_ID}`, {waitUntil: 'domcontentloaded'});

  await expect(page.getByRole('heading', {level: 1, name: 'ASHRAE HVAC (archive)'})).toBeVisible();
});

test('an id neither the schedule nor the archive has is not found', async ({page}) => {
  await mockArchiveWithout(page);
  await mockSchedule(page, currentSchedule());
  await page.goto(`/projects/${HVAC_SLOT_ID}`, {waitUntil: 'domcontentloaded'});

  await expect(page.getByRole('heading', {level: 1, name: "We couldn't find this project"})).toBeVisible();
});

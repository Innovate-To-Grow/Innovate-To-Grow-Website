// /past-projects/:shareId when the list cannot be shown: a link to a list that does not exist says the list
// isn't available; any other failure (server error, network) says the list couldn't be loaded and offers to
// try again, since the link itself may be fine.
import type {PastProjectShare} from '../../src/features/projects/api';
import {expect, test} from '../helpers/fixtures';

const SHARE_ID = '7d7f3f5e-2b8a-4c55-9a51-0f6f7f1c2a10';

const share: PastProjectShare = {
  id: SHARE_ID,
  name: 'Water projects',
  rows: [
    {
      id: '5970763b-cf7c-40d6-a87c-96916e0ea695',
      semester_label: '2026 Spring',
      class_code: 'CAP',
      team_number: '101',
      team_name: 'HVAC Regulators',
      project_title: 'ASHRAE HVAC Design Calculations',
      organization: 'ASHRAE - Sierra Delta',
      industry: 'Energy',
      abstract: 'A complete HVAC system design.',
      student_names: 'Brian Arroyo, Joel Gonzalez',
      is_presenting: 'Yes',
    },
  ],
  note: '',
  details_text: '',
  version: 1,
  share_url: `/past-projects/${SHARE_ID}`,
  can_edit: false,
  created_at: '2026-05-01T00:00:00Z',
};

const SHARE_URL = /\/projects\/past-shares\/[^/]+\/?(\?.*)?$/;
const json = (body: unknown, status = 200) => ({status, contentType: 'application/json', body: JSON.stringify(body)});

test('a link to a list that does not exist says the list is not available', async ({page}) => {
  await page.route(SHARE_URL, (route) => route.fulfill(json({detail: 'Not found.'}, 404)));
  await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

  await expect(page.getByRole('heading', {level: 1, name: "This shared list isn't available"})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Try again'})).toHaveCount(0);
});

test('a list that fails to load can be tried again', async ({page}) => {
  let requests = 0;
  await page.route(SHARE_URL, (route) => {
    requests += 1;
    return route.fulfill(requests === 1 ? json({detail: 'Server error.'}, 500) : json(share));
  });
  await page.goto(`/past-projects/${SHARE_ID}`, {waitUntil: 'domcontentloaded'});

  await expect(page.getByRole('heading', {level: 1, name: "We couldn't load this shared list"})).toBeVisible();
  await expect(page.getByText("This shared list isn't available")).toHaveCount(0);

  await page.getByRole('button', {name: 'Try again'}).click();

  await expect(page.getByRole('heading', {level: 1, name: 'Water projects'})).toBeVisible();
  await expect(page.getByText('ASHRAE HVAC Design Calculations').first()).toBeVisible();
});

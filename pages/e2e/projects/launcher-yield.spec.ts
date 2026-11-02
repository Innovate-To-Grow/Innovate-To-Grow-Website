// The chat launcher on a projects page (data-launcher-avoid on the page root): it tucks into the gutter over the
// list's text and rows, not only over controls, comes back whole where nothing is under it (the room the footer's
// navy bar keeps under its links at the page end) and whenever it has keyboard focus. Phones and tablets only: a
// desktop's corner sits in the margin beside the 1170px column.
import type {Page} from '@playwright/test';

import {test, expect} from '../helpers/fixtures';
import {assistantConfig, mockAssistantConfig, mockSchedule, schedulePayload} from '../helpers';

/** Sixty teams on one page: the list runs several screens long at any phone or tablet width. */
function longSchedule() {
  const projects = Array.from({length: 60}, (_, i) => ({
    id: `project-e2e-${i + 1}`,
    track: 0,
    order: i + 1,
    year_semester: '2026 Spring',
    class_code: 'CAP',
    team_number: `${i + 1}`,
    team_name: `Team ${i + 1}`,
    project_title: `Project Title ${i + 1}`,
    organization: `Org ${i + 1}`,
    industry: i % 2 === 0 ? 'Software' : 'Hardware',
    abstract: `Abstract for project ${i + 1}.`,
    student_names: `Student ${i + 1}`,
    is_presenting: true,
    tooltip: '',
  }));
  return schedulePayload({projects});
}

/** The footer's navy bar, which keeps 88px under its links for the launcher at 768px and below. */
const FOOTER_LAYOUT = {
  menus: [],
  footer: {
    id: 'footer-e2e',
    name: 'Footer',
    slug: 'footer',
    content: {
      copyright: '© 2026 UC Regents',
      footer_links: [
        {label: 'Privacy', href: '/privacy'},
        {label: 'Accessibility', href: '/accessibility'},
      ],
    },
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  homepage_route: '/',
};

const launcher = (page: Page) => page.locator('.itg-assistant__launcher');

/** The tab's width: 12px in the 20px gutter at 992px and below, 16px in the 24px gutter above. */
const tabWidth = (page: Page) => page.evaluate(() => (window.innerWidth <= 992 ? 12 : 16));

const box = (page: Page) =>
  launcher(page).evaluate((element) => {
    const {left, right, width, height} = element.getBoundingClientRect();
    return {left, right, width, height, viewport: document.documentElement.clientWidth};
  });

/** Scrolls by script, so no pointer or key input counts towards :focus-visible. */
const scrollTo = (page: Page, where: 'middle' | 'end') =>
  page.evaluate((target) => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    window.scrollTo(0, target === 'end' ? document.documentElement.scrollHeight : Math.round(max / 2));
  }, where);

test.beforeEach(async ({page}) => {
  await mockAssistantConfig(page, assistantConfig());
  await mockSchedule(page, longSchedule());
  await page.route('**/layout/', (route) => route.fulfill({json: FOOTER_LAYOUT}));
  await page.goto('/current-projects?per=50', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.project-grid-count')).toContainText('60 projects');
  await expect(launcher(page)).toBeVisible();
});

test('tucks into the gutter over the list in the middle of the page', {tag: '@mobile-only'}, async ({page}) => {
  await scrollTo(page, 'middle');

  await expect(launcher(page)).toHaveClass(/\bis-tucked\b/);
  const expected = await tabWidth(page);
  await expect.poll(async () => (await box(page)).width).toBe(expected);
  const {right, height, viewport} = await box(page);
  expect(height).toBe(56);
  expect(right).toBe(viewport);
});

test('comes back whole over the footer at the end of the page', {tag: '@mobile-only'}, async ({page}) => {
  test.skip((page.viewportSize()?.width ?? 0) > 768, 'The footer reserves room under the launcher only at 768px and below.');
  await expect(page.locator('.footer-bottom')).toBeVisible();
  await scrollTo(page, 'end');

  await expect(launcher(page)).not.toHaveClass(/\bis-tucked\b/);
  const {width, height} = await box(page);
  expect([width, height]).toEqual([56, 56]);
});

test('comes back whole while it has keyboard focus', {tag: '@mobile-only'}, async ({page}) => {
  await scrollTo(page, 'middle');
  await expect(launcher(page)).toHaveClass(/\bis-tucked\b/);
  const expected = await tabWidth(page);

  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  // #chatbot-root is the last root in the page, so Shift+Tab from nothing reaches the launcher first.
  for (let press = 0; press < 3; press += 1) {
    await page.keyboard.press('Shift+Tab');
    if (await launcher(page).evaluate((element) => element === document.activeElement)) break;
  }
  await expect(launcher(page)).toBeFocused();
  await expect.poll(async () => (await box(page)).width).toBe(56);

  await page.keyboard.press('Tab');
  await expect(launcher(page)).not.toBeFocused();
  await expect.poll(async () => (await box(page)).width).toBe(expected);
});

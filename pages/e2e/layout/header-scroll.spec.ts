// Desktop header on scroll: the blue bar scrolls away, only the white menu
// row stays pinned, and the round i2G logo joins its front.
// The menu row's date shows whenever it fits, the same at the top and pinned.
import type {Page} from '@playwright/test';
import {test, expect} from '../helpers/fixtures';
import {seedAuthenticatedSession} from '../helpers';

const SCROLLED_Y = 600;

const item = (title: string, url: string, children: string[] = []) => ({
  type: 'app',
  title,
  icon: '',
  open_in_new_tab: false,
  url,
  children: children.map((child) => ({
    type: 'app',
    title: child,
    icon: '',
    open_in_new_tab: false,
    url: `${url}/${child.toLowerCase().replace(/\W+/g, '-')}`,
    children: [],
  })),
});

// The production menu's eight sections.
const MAIN_MENU = [
  item('Home', '/'),
  item('About', '/about', ['Engineering Capstone', 'Software Eng. Capstone']),
  item('Events', '/event', ['Event Info', 'Schedule', 'Past Events']),
  item('Projects', '/projects', ['Current Projects', 'Past Projects']),
  item('Partner with Us', '/partnership', ['Newsletter', 'FAQs']),
  item('Students', '/students', ['For Students']),
  item('Project Submission', '/project-submission'),
  item('News', '/news'),
];

async function mockMainMenu(page: Page, items = MAIN_MENU, delayMs = 0) {
  await page.route('**/layout/', async (route) => {
    if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        menus: [{id: 'menu-e2e', name: 'main', display_name: 'Main', items}],
        footer: null,
        homepage_route: '/',
      }),
    });
  });
}

const signInAs = async (page: Page) => {
  const name = {first_name: 'Hongzhe', last_name: 'Xie'};
  await seedAuthenticatedSession(page, {user: {...name, email: 'member@example.com'}, profile: name});
};

async function openPage(page: Page, width: number, items = MAIN_MENU) {
  await page.setViewportSize({width, height: 900});
  await mockMainMenu(page, items);
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.addStyleTag({content: '#footer-root { min-height: 3000px; }'});
  await expect(page.locator('.site-header-nav .menu-bar-item')).toHaveCount(items.length);
  await page.evaluate(() => document.fonts.ready);
}

const scrollTo = (page: Page, y: number) => page.evaluate((top) => window.scrollTo(0, top), y);

const rowState = (page: Page) =>
  page.evaluate(() => {
    const rect = (element: Element | null) => (element ? element.getBoundingClientRect() : null);
    const shown = (element: Element | null) => {
      if (!element) return false;
      const style = getComputedStyle(element);
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > 0.5;
    };
    const items = Array.from(document.querySelectorAll('.site-header-nav .menu-bar-item'));
    const logo = document.querySelector('.site-header-menu-logo');
    const date = document.querySelector('.site-header-date');
    const label = document.querySelector('.member-label');
    const member = document.querySelector('.member-button, .member-signin');
    const range = document.createRange();
    range.selectNodeContents(items[0].querySelector('.menu-bar-link span') ?? items[0]);
    return {
      firstLabelLeft: Math.round(range.getBoundingClientRect().left),
      logoRight: Math.round(rect(logo)!.right),
      utilityLeft: Math.round(rect(document.querySelector('.site-header-utility'))!.left),
      memberWidth: Math.round(rect(member)?.width ?? 0),
      condensed: document.querySelector('.site-header')!.classList.contains('is-condensed'),
      rowTop: Math.round(rect(document.querySelector('.site-header-menu'))!.top),
      barBottom: Math.round(rect(document.querySelector('.site-header-bar'))!.bottom),
      mainTop: Math.round(rect(document.getElementById('main'))!.top + window.scrollY),
      rows: new Set(items.map((li) => Math.round(li.getBoundingClientRect().top))).size,
      logoShown: shown(logo),
      logoLeft: Math.round(rect(logo)!.left),
      contentLeft: Math.round(
        rect(document.querySelector('.site-header-menu-inner'))!.left +
          parseFloat(getComputedStyle(document.querySelector('.site-header-menu-inner')!).paddingLeft),
      ),
      dateShown: shown(date),
      labelCut: label ? label.scrollWidth > label.clientWidth + 0.5 : false,
    };
  });


/** Waits until the pinned row shows its logo and every transition has finished (positions are final). */
const waitForPinnedRow = async (page: Page) => {
  await expect.poll(async () => (await rowState(page)).logoShown).toBe(true);
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
};

test('scrolling pins only the white menu row, with the round i2G logo at its front', async ({page}) => {
  await openPage(page, 1440);

  const top = await rowState(page);
  expect(top.condensed).toBe(false);
  expect(top.logoShown).toBe(false);
  // The menu row follows the blue bar directly (no site-name band).
  expect(top.rowTop).toBe(top.barBottom);

  await scrollTo(page, SCROLLED_Y);
  await waitForPinnedRow(page);
  const pinned = await rowState(page);
  expect(pinned.condensed).toBe(true);
  expect(pinned.rowTop).toBe(0);
  // The blue bar has scrolled away with the page.
  expect(pinned.barBottom).toBeLessThanOrEqual(0);
  expect(pinned.logoLeft).toBe(pinned.contentLeft);
  expect(pinned.rows).toBe(1);
  // Nothing in the page moved when the row pinned.
  expect(pinned.mainTop).toBe(top.mainTop);
  // The items step aside by the 43px logo slot, clear of the logo; the right end stays put.
  expect(pinned.firstLabelLeft - top.firstLabelLeft).toBe(43);
  expect(pinned.firstLabelLeft - pinned.logoRight).toBeGreaterThanOrEqual(12);
  expect(pinned.utilityLeft).toBe(top.utilityLeft);
  await expect(page.locator('.site-header-menu').getByRole('link', {name: 'Innovate To Grow home'})).toHaveAttribute('href', '/');

  await scrollTo(page, 0);
  await expect.poll(async () => (await rowState(page)).logoShown).toBe(false);
  expect((await rowState(page)).condensed).toBe(false);
});

test('the row condenses exactly when it pins, and lets go 8px before it unpins', async ({page}) => {
  await openPage(page, 1280);
  const pinAt = await page.evaluate(() => document.querySelector('.site-header-bar')!.getBoundingClientRect().height);
  const condensedAt = async (y: number) => {
    await scrollTo(page, y);
    await page.waitForTimeout(150);
    return (await rowState(page)).condensed;
  };
  expect(await condensedAt(Math.ceil(pinAt) - 2)).toBe(false);
  expect(await condensedAt(Math.ceil(pinAt))).toBe(true);
  expect(await condensedAt(Math.ceil(pinAt) - 8)).toBe(true);
  expect(await condensedAt(Math.ceil(pinAt) - 10)).toBe(false);
});

test('with reduced motion the logo and the items switch without transitions', async ({page}) => {
  await page.emulateMedia({reducedMotion: 'reduce'});
  await openPage(page, 1440);
  await scrollTo(page, SCROLLED_Y);
  await waitForPinnedRow(page);
  const durations = await page.evaluate(() =>
    ['.menu-bar-list', '.site-header-menu-logo'].map((selector) => getComputedStyle(document.querySelector(selector)!).transitionDuration),
  );
  for (const duration of durations) expect(duration.split(',').every((part) => parseFloat(part) === 0)).toBe(true);
});

// Signed in as "Hongzhe Xie" the date fits from about 1182px up.
const DATE_SHOWN: Record<number, boolean> = {1440: true, 1200: true, 1100: false, 993: false};

for (const width of [1440, 1200, 1100, 993]) {
  test(`at ${width}px the menu keeps one row and the date shows or hides the same way at the top and pinned`, async ({page}) => {
    await signInAs(page);
    await openPage(page, width);
    await expect(page.locator('.member-label')).toHaveText(/hongzhe xie/i);
    await expect.poll(async () => (await rowState(page)).dateShown).toBe(DATE_SHOWN[width]);

    const top = await rowState(page);
    await scrollTo(page, SCROLLED_Y);
    await waitForPinnedRow(page);
    const pinned = await rowState(page);

    expect(top.rows).toBe(1);
    expect(pinned.rows).toBe(1);
    expect(top.dateShown).toBe(DATE_SHOWN[width]);
    expect(pinned.dateShown).toBe(top.dateShown);
    // The date goes before the member's name is cut.
    expect(top.labelCut || pinned.labelCut).toBe(false);
  });
}

test('signed out, the date shows wherever it fits beside "Sign in"', async ({page}) => {
  await openPage(page, 1140);
  // Below 1200px the date starts hidden until the real menu has been measured (one frame later).
  await expect.poll(async () => (await rowState(page)).dateShown).toBe(true);
  await expect(page.locator('.member-signin')).toHaveText(/^sign in$/i);
  await scrollTo(page, SCROLLED_Y);
  await waitForPinnedRow(page);
  expect((await rowState(page)).dateShown).toBe(true);
});

test('a first visit decides the date on the real menu, not on the loading skeleton', async ({page}) => {
  await signInAs(page);
  // Watch every frame for a visible date while the menu is still loading.
  await page.addInitScript(() => {
    const flags = window as unknown as {dateWasShown: boolean};
    flags.dateWasShown = false;
    const watch = () => {
      const date = document.querySelector('.site-header-date');
      if (date && getComputedStyle(date).visibility !== 'hidden' && getComputedStyle(date).position !== 'absolute') {
        flags.dateWasShown = true;
      }
      requestAnimationFrame(watch);
    };
    requestAnimationFrame(watch);
  });
  await page.setViewportSize({width: 1130, height: 900});
  await mockMainMenu(page, MAIN_MENU, 800);
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.site-header-nav .menu-bar-item')).toHaveCount(8);
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => (window as unknown as {dateWasShown: boolean}).dateWasShown)).toBe(false);
});

test('a longer CMS menu shortens the member name before it wraps, the same way at the top and pinned', async ({page}) => {
  await signInAs(page);
  const longer = [...MAIN_MENU, item('Contact Us', '/contact'), item('Resources', '/resources')];
  await openPage(page, 993, longer);
  const top = await rowState(page);
  await scrollTo(page, SCROLLED_Y);
  await waitForPinnedRow(page);
  const pinned = await rowState(page);

  // The member link never collapses, and pinning changes nothing in the row's layout.
  expect(top.memberWidth).toBeGreaterThanOrEqual(80);
  expect(pinned.memberWidth).toBe(top.memberWidth);
  expect(pinned.rows).toBe(top.rows);
  expect(pinned.mainTop).toBe(top.mainTop);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('focusing the pinned row does not scroll the page, and Shift+Tab out of it scrolls back to what gets focus', async ({page}) => {
  await openPage(page, 1200);
  await scrollTo(page, SCROLLED_Y);
  await waitForPinnedRow(page);

  await page.locator('.site-header-menu-logo').focus();
  await page.keyboard.press('Tab');
  await expect(page.locator('.site-header-nav .menu-bar-link').first()).toBeFocused();
  expect(await page.evaluate(() => window.scrollY)).toBe(SCROLLED_Y);

  // Back past the logo: the blue bar's last link has scrolled away, so focusing it brings it back on screen.
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Shift+Tab');
  await expect(page.locator('.site-header-bar').getByRole('link', {name: 'Give'})).toBeFocused();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const box = document.activeElement!.getBoundingClientRect();
        return box.top >= 0 && box.bottom <= window.innerHeight;
      }),
    )
    .toBe(true);
});

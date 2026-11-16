import type {Page} from '@playwright/test';
import {expect} from '../helpers/fixtures';
import {seedAuthenticatedSession} from '../helpers';

export const SCROLLED_Y = 600;

export const item = (title: string, url: string, children: string[] = []) => ({
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
export const MAIN_MENU = [
  item('Home', '/'),
  item('About', '/about', ['Engineering Capstone', 'Software Eng. Capstone']),
  item('Events', '/event', ['Event Info', 'Schedule', 'Past Events']),
  item('Projects', '/projects', ['Current Projects', 'Past Projects']),
  item('Partner with Us', '/partnership', ['Newsletter', 'FAQs']),
  item('Students', '/students', ['For Students']),
  item('Project Submission', '/project-submission'),
  item('News', '/news'),
];

export async function mockMainMenu(page: Page, items = MAIN_MENU, delayMs = 0) {
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

export const signInAs = async (page: Page) => {
  const name = {first_name: 'Hongzhe', last_name: 'Xie'};
  await seedAuthenticatedSession(page, {user: {...name, email: 'member@example.com'}, profile: name});
};

export async function openPage(page: Page, width: number, {items = MAIN_MENU, signedIn = false} = {}) {
  await page.setViewportSize({width, height: 900});
  await mockMainMenu(page, items);
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  // The header mounts before the lazy route. Wait for its final content: the
  // login form can shift scroll anchoring, and a signed-in visit redirects to
  // /account and resets scroll to zero. Neither may race the scroll assertions.
  await expect(page.getByRole('main').getByRole('heading', {
    level: 1,
    name: signedIn ? 'Account Dashboard' : 'Welcome to I2G',
    exact: true,
  })).toBeVisible();
  await page.addStyleTag({content: '#footer-root { min-height: 3000px; }'});
  await expect(page.locator('.site-header-nav .menu-bar-item')).toHaveCount(items.length);
  await page.evaluate(() => document.fonts.ready);
}

export const scrollTo = (page: Page, y: number) => page.evaluate((top) => window.scrollTo(0, top), y);

export const rowState = (page: Page) =>
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
export const waitForPinnedRow = async (page: Page) => {
  await expect.poll(async () => (await rowState(page)).logoShown).toBe(true);
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
};

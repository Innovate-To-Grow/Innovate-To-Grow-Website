import {test, expect} from '../../helpers/fixtures';
import {
  item,
  MAIN_MENU,
  mockMainMenu,
  openPage,
  rowState,
  SCROLLED_Y,
  scrollTo,
  signInAs,
  waitForPinnedRow,
} from './headerScrollFixtures';

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
    await openPage(page, width, {signedIn: true});
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
  await openPage(page, 993, {items: longer, signedIn: true});
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

// Mobile-only responsive behavior. These run on the mobile/tablet projects
// (grep /@mobile-only/) and use touch taps. The off-canvas drawer is
// MobileMenuPanel (#mobile-menu); the hamburger lives in #menu-root.
import {test, expect} from '../helpers/fixtures';
import {expectSignedOut, seedAuthenticatedSession} from '../helpers';

test('mobile menu drawer opens and shows the sign-in CTA', {tag: '@mobile-only'}, async ({page}) => {
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.locator('#menu-root').getByRole('button', {name: 'Toggle menu'}).tap();

  await expect(page.locator('#mobile-menu')).toHaveClass(/is-open/);
  await expect(page.locator('#mobile-menu').getByRole('button', {name: /sign in \/ sign up/i})).toBeVisible();
});

test('mobile sign-in CTA routes to /login', {tag: '@mobile-only'}, async ({page}) => {
  await page.goto('/forgot-password', {waitUntil: 'domcontentloaded'});
  await page.locator('#menu-root').getByRole('button', {name: 'Toggle menu'}).tap();
  await page.locator('#mobile-menu').getByRole('button', {name: /sign in \/ sign up/i}).tap();
  await expect(page).toHaveURL(/\/login$/);
});

test('phone and tablet header: one blue bar, a cross while open, a one-size-smaller menu', {tag: '@mobile-only'}, async ({page}) => {
  const link = (title: string, url: string, children: string[] = []) => ({
    type: 'app', title, icon: '', open_in_new_tab: false, url,
    children: children.map((child, index) => ({type: 'app', title: child, icon: '', open_in_new_tab: false, url: `${url}/${index}`, children: []})),
  });
  await page.route('**/layout/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        menus: [{id: 'menu-e2e', name: 'main', display_name: 'Main', items: [link('Home', '/'), link('Events', '/event', ['Schedule']), link('News', '/news')]}],
        footer: null,
        homepage_route: '/',
      }),
    }),
  );
  await page.goto('/login', {waitUntil: 'domcontentloaded'});

  const viewport = page.viewportSize()!;
  const bar = await page.locator('.site-header-bar').boundingBox();
  expect(bar).toEqual({x: 0, y: 0, width: viewport.width, height: 61});
  await expect(page.locator('.site-header-band')).toHaveCount(0);
  // The UC Merced wordmark at the top of the page; the round i2G logo once scrolled.
  const wordmark = page.locator('.site-header-bar').getByRole('link', {name: 'UC Merced'});
  const logo = page.locator('.site-header-bar').getByRole('link', {name: 'Innovate To Grow home'});
  await expect(wordmark).toBeVisible();
  await expect(logo).toBeHidden();
  await page.addStyleTag({content: '#footer-root { min-height: 3000px; }'});
  await page.evaluate(() => window.scrollTo(0, 300));
  await expect(logo).toBeVisible();
  await expect(wordmark).toBeHidden();
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(wordmark).toBeVisible();

  const toggle = page.locator('#menu-root').getByRole('button', {name: 'Toggle menu'});
  await toggle.tap();
  const panel = page.locator('#mobile-menu');
  await expect(panel).toBeVisible();
  // The three bars turn into a cross.
  await expect
    .poll(() =>
      toggle.locator('.site-header-mobile-toggle-bar').evaluateAll((bars) =>
        bars.map((element) => {
          const style = getComputedStyle(element);
          return style.transform === 'none' ? Number(style.opacity) : 'turned';
        }),
      ),
    )
    .toEqual(['turned', 0, 'turned']);

  await panel.getByRole('button', {name: 'Events pages'}).tap();
  const sizes = await panel.evaluate((element) => ({
    item: getComputedStyle(element.querySelector('.header-mobile-link')!).fontSize,
    subItem: getComputedStyle(element.querySelector('.header-mobile-sublink')!).fontSize,
    shortestTarget: Math.min(
      ...Array.from(element.querySelectorAll<HTMLElement>('a, button'))
        .filter((target) => target.getClientRects().length > 0)
        .map((target) => target.getBoundingClientRect().height),
    ),
  }));
  expect(sizes).toEqual({item: '16px', subItem: '13px', shortestTarget: expect.any(Number)});
  expect(sizes.shortestTarget).toBeGreaterThanOrEqual(44);

  // A tap on the dimmed page under the menu closes it.
  await page.touchscreen.tap(viewport.width / 2, viewport.height - 10);
  await expect(panel).toBeHidden();
});

test('mobile drawer shows the member and signs out', {tag: '@mobile-only'}, async ({page}) => {
  await seedAuthenticatedSession(page, {user: {email: 'mobile@example.com'}});
  await page.route('**/authn/logout/', (route) => route.fulfill({status: 205, body: ''}));

  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  await page.locator('#menu-root').getByRole('button', {name: 'Toggle menu'}).tap();

  await expect(page.locator('.header-mobile-member')).toContainText('mobile@example.com');
  await page.locator('.header-mobile-member').getByRole('button', {name: 'Sign Out'}).tap();

  await expectSignedOut(page);
});

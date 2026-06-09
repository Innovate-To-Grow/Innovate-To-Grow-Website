// Mobile-only responsive behavior. These run on the mobile/tablet projects
// (grep /@mobile-only/) and use touch taps. The off-canvas drawer is
// MobileMenuPanel (#mobile-menu); the hamburger lives in #menu-root.
import {test, expect} from './fixtures';
import {expectSignedOut, seedAuthenticatedSession} from './helpers';

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

test('mobile drawer shows the member and signs out', {tag: '@mobile-only'}, async ({page}) => {
  await seedAuthenticatedSession(page, {user: {email: 'mobile@example.com'}});
  await page.route('**/authn/logout/', (route) => route.fulfill({status: 205, body: ''}));

  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  await page.locator('#menu-root').getByRole('button', {name: 'Toggle menu'}).tap();

  await expect(page.locator('.header-mobile-member')).toContainText('mobile@example.com');
  await page.locator('.header-mobile-member').getByRole('button', {name: 'Sign Out'}).tap();

  await expectSignedOut(page);
});

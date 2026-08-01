// The flagship integration test: auth state must propagate across the three
// independent React roots via the `i2g-auth-state-change` event. We observe it
// through #menu-root's member button (Sign In ⇄ member email). Tagged @core so
// it also runs on every mobile/tablet device.
import {test, expect} from '../fixtures';
import {
  expectSignedInAs,
  expectSignedOut,
  loginResponse,
  mockEmailAuthFlow,
  mockProfileEndpoint,
  profileResponse,
  seedAuthenticatedSession,
} from '../helpers';

test('logged-out load shows Sign In in the menu root', {tag: '@core'}, async ({page}) => {
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await expectSignedOut(page);
});

test('expired access bootstraps through refresh and authoritative session state', async ({page}) => {
  const email = 'bootstrap@example.com';
  const seeded = await seedAuthenticatedSession(page, {
    user: {email},
    accessExp: Math.floor(Date.now() / 1000) - 60,
  });
  let sessionRequests = 0;
  await page.route('**/authn/session/', (route) => {
    sessionRequests += 1;
    if (sessionRequests === 1) {
      return route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({detail: 'expired'}),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user: {...seeded.profileRef.current, phone: '', is_staff: false},
        requires_profile_completion: false,
        next_step: 'account',
      }),
    });
  });

  await page.goto('/account', {waitUntil: 'domcontentloaded'});

  await expectSignedInAs(page, email);
  expect(sessionRequests).toBe(2);
  const keys = await page.evaluate(() => ({
    session: localStorage.getItem('i2g_auth_session'),
    access: localStorage.getItem('i2g_access_token'),
    refresh: localStorage.getItem('i2g_refresh_token'),
    user: localStorage.getItem('i2g_user'),
  }));
  expect(keys.session).not.toBeNull();
  expect(keys.access).toBeNull();
  expect(keys.refresh).toBeNull();
  expect(keys.user).toBeNull();
});

test('login in #root flips #menu-root to the member email', {tag: '@core'}, async ({page}) => {
  const email = 'sync-login@example.com';
  await mockEmailAuthFlow(page, {
    verifyResponse: loginResponse({user: {email, member_uuid: 'm-sync'}}),
  });
  // After login the app lands on /account — stub its mount side-effects so the
  // navigation target doesn't hang on un-mocked network.
  await mockProfileEndpoint(page, {current: profileResponse({email})});
  await page.route('**/event/my-tickets/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
  await page.route('**/event/registration-events/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
  await page.route('**/event/registration-options/**', (route) =>
    route.fulfill({status: 404, contentType: 'application/json', body: JSON.stringify({detail: 'none'})}),
  );

  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await expectSignedOut(page);

  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', {name: 'Continue', exact: true}).click();
  await expect(page).toHaveURL(/\/verify-email\?flow=auth/);

  await page.getByLabel('6-digit verification code').fill('123456');
  await page.getByRole('button', {name: 'Continue', exact: true}).click();

  await expectSignedInAs(page, email);
});

test('Sign Out flips #menu-root back to Sign In; footer never shows auth', {tag: '@core'}, async ({page}) => {
  const email = 'sign-out@example.com';
  await seedAuthenticatedSession(page, {user: {email}});
  await page.route('**/authn/logout/', (route) => route.fulfill({status: 205, body: ''}));

  await page.goto('/account', {waitUntil: 'domcontentloaded'});
  await expectSignedInAs(page, email);

  await page.locator('#root').getByRole('button', {name: /sign out/i}).click();

  await expectSignedOut(page);
  await expect(page.locator('#footer-root').getByRole('button', {name: /sign out/i})).toHaveCount(0);
});

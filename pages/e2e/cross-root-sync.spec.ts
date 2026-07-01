// The flagship integration test: auth state must propagate across the three
// independent React roots via the `i2g-auth-state-change` event. We observe it
// through #menu-root's member button (Sign In ⇄ member email). Tagged @core so
// it also runs on every mobile/tablet device.
import {test, expect} from './fixtures';
import {
  expectSignedInAs,
  expectSignedOut,
  loginResponse,
  mockEmailAuthFlow,
  mockProfileEndpoint,
  profileResponse,
  seedAuthenticatedSession,
} from './helpers';

test('logged-out load shows Sign In in the menu root', {tag: '@core'}, async ({page}) => {
  await page.goto('/', {waitUntil: 'domcontentloaded'});
  await expectSignedOut(page);
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
  await page.route('**/event/registration-options/', (route) =>
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

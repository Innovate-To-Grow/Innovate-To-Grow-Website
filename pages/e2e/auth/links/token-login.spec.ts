// Token login entry points POST a token, persist sessions where appropriate,
// and render success/error states. A login link that cannot be used is not an
// error: it falls back to signing in with an emailed code, inline on
// /login-link. The retired /unsubscribe-login link only redirects to /account.
import {test, expect} from '../../helpers/fixtures';
import {
  expectSignedInAs,
  mockAccountDashboard,
} from '../../helpers';
import {
  cases,
  ERROR_MARKUP,
  SUCCESS,
} from './tokenLoginFixtures';

for (const c of cases) {
  test(`${c.name}-login success flips the menu to the member email`, c.name === 'login-link' ? {tag: '@core'} : {}, async ({page}) => {
    await mockAccountDashboard(page, {email: SUCCESS.user.email});
    await page.route(c.endpoint, (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(SUCCESS)}),
    );
    await page.goto(`${c.path}?token=ok`, {waitUntil: 'domcontentloaded'});
    await expectSignedInAs(page, SUCCESS.user.email);
  });

  if (c.fallback) {
    test(`${c.name}-login invalid token falls back to the email-code sign-in instead of an error`, async ({page}) => {
      await page.route(c.endpoint, (route) =>
        route.fulfill({status: 400, contentType: 'application/json', body: JSON.stringify({detail: 'bad token'})}),
      );
      await page.goto(`${c.path}?token=bad`, {waitUntil: 'domcontentloaded'});
      await expect(page.getByText(c.invalidText)).toBeVisible();
      await expect(page.getByLabel('Email address')).toBeVisible();
      await expect(page.locator(ERROR_MARKUP)).toHaveCount(0);
      expect(new URL(page.url()).searchParams.has('token')).toBe(false);
    });

    test(`${c.name}-login with no token falls back to the email-code sign-in`, async ({page}) => {
      await page.goto(c.path, {waitUntil: 'domcontentloaded'});
      await expect(page.getByText(c.noTokenText)).toBeVisible();
      await expect(page.getByLabel('Email address')).toBeVisible();
      await expect(page.locator(ERROR_MARKUP)).toHaveCount(0);
    });
  } else {
    test(`${c.name}-login invalid token shows error and Go to Login`, async ({page}) => {
      await page.route(c.endpoint, (route) =>
        route.fulfill({status: 400, contentType: 'application/json', body: JSON.stringify({detail: 'bad token'})}),
      );
      await page.goto(`${c.path}?token=bad`, {waitUntil: 'domcontentloaded'});
      await expect(page.getByText(c.invalidText)).toBeVisible();
      await expect(page.getByRole('link', {name: 'Go to Login'})).toBeVisible();
      expect(new URL(page.url()).searchParams.has('token')).toBe(false);
    });

    test(`${c.name}-login with no token shows the guard message`, async ({page}) => {
      await page.goto(c.path, {waitUntil: 'domcontentloaded'});
      await expect(page.getByText(c.noTokenText)).toBeVisible();
    });
  }
}

test('login-link accepts a fragment token and scrubs it before exchange', async ({page}) => {
  await mockAccountDashboard(page, {email: SUCCESS.user.email});
  await page.route('**/mail/login-link/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(SUCCESS)}),
  );
  await page.goto('/login-link#token=fragment-secret', {waitUntil: 'domcontentloaded'});

  await expect(page).toHaveURL(/\/account$/);
  expect(new URL(page.url()).hash).toBe('');
  await expectSignedInAs(page, SUCCESS.user.email);
});

test('login-link rejection with a stored session continues to /account', async ({page}) => {
  // First click: token exchange succeeds and persists the session.
  await mockAccountDashboard(page, {email: SUCCESS.user.email});
  await page.route('**/mail/login-link/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(SUCCESS)}),
  );
  await page.goto('/login-link?token=once', {waitUntil: 'domcontentloaded'});
  await expectSignedInAs(page, SUCCESS.user.email);

  // Second click on the (now consumed) one-time link: backend rejects, but the
  // stored session should route the member to /account instead of an error.
  await page.unroute('**/mail/login-link/');
  await page.route('**/mail/login-link/', (route) =>
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({detail: 'This login link has already been used.', code: 'already_used'}),
    }),
  );
  await page.goto('/login-link?token=once', {waitUntil: 'domcontentloaded'});
  await page.waitForURL('**/account**');
  await expect(page.getByLabel('Email address')).toHaveCount(0);
  await expect(page.locator(ERROR_MARKUP)).toHaveCount(0);
});

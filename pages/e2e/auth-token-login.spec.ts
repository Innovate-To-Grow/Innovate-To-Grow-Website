// The five token auto-login entry points. Each POSTs a token, persists the
// session, dispatches the cross-root event, and navigates. We assert the menu
// flip (success) and the error/guard text + "Go to Login" link (failure).
import {test, expect} from './fixtures';
import {expectSignedInAs, loginResponse, mockAccountDashboard} from './helpers';

const SUCCESS = loginResponse({user: {email: 'token-login@example.com', member_uuid: 'm-token'}});

const INVALID_LOGIN = 'This login link is invalid or has expired. Please log in manually.';
const NO_TOKEN = 'No login token provided.';

interface TokenCase {
  name: string;
  path: string;
  endpoint: string;
  invalidText: string;
  noTokenText: string;
}

const cases: TokenCase[] = [
  {name: 'magic', path: '/magic-login', endpoint: '**/mail/magic-login/', invalidText: INVALID_LOGIN, noTokenText: NO_TOKEN},
  {name: 'ticket', path: '/ticket-login', endpoint: '**/event/ticket-login/', invalidText: INVALID_LOGIN, noTokenText: NO_TOKEN},
  {name: 'unsubscribe', path: '/unsubscribe-login', endpoint: '**/authn/unsubscribe-login/', invalidText: INVALID_LOGIN, noTokenText: NO_TOKEN},
  {
    name: 'impersonate',
    path: '/impersonate-login',
    endpoint: '**/authn/impersonate-login/',
    invalidText: 'This impersonation link is invalid or has expired.',
    noTokenText: 'No impersonation token provided.',
  },
];

for (const c of cases) {
  test(`${c.name}-login success flips the menu to the member email`, c.name === 'magic' ? {tag: '@core'} : {}, async ({page}) => {
    await mockAccountDashboard(page, {email: SUCCESS.user.email});
    await page.route(c.endpoint, (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(SUCCESS)}),
    );
    await page.goto(`${c.path}?token=ok`, {waitUntil: 'domcontentloaded'});
    await expectSignedInAs(page, SUCCESS.user.email);
  });

  test(`${c.name}-login invalid token shows error and Go to Login`, async ({page}) => {
    await page.route(c.endpoint, (route) =>
      route.fulfill({status: 400, contentType: 'application/json', body: JSON.stringify({detail: 'bad token'})}),
    );
    await page.goto(`${c.path}?token=bad`, {waitUntil: 'domcontentloaded'});
    await expect(page.getByText(c.invalidText)).toBeVisible();
    await expect(page.getByRole('link', {name: 'Go to Login'})).toBeVisible();
  });

  test(`${c.name}-login with no token shows the guard message`, async ({page}) => {
    await page.goto(c.path, {waitUntil: 'domcontentloaded'});
    await expect(page.getByText(c.noTokenText)).toBeVisible();
  });
}

test('email-auth-link verifies the code and signs the member in', {tag: '@core'}, async ({page}) => {
  const email = 'link-auth@example.com';
  await mockAccountDashboard(page, {email});
  await page.route('**/authn/email-auth/verify-code/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(loginResponse({user: {email, member_uuid: 'm-link'}})),
    }),
  );
  await page.goto(`/email-auth-link?flow=auth&source=subscribe&email=${encodeURIComponent(email)}&code=123456`, {
    waitUntil: 'domcontentloaded',
  });
  await expectSignedInAs(page, email);
});

test('email-auth-link with malformed params shows the guard error', async ({page}) => {
  await page.goto('/email-auth-link?flow=auth&source=subscribe&email=x@example.com', {waitUntil: 'domcontentloaded'});
  await expect(page.getByText('This email link is invalid or incomplete.')).toBeVisible();
});

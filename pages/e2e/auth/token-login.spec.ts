// Token login entry points POST a token, persist sessions where appropriate,
// and render success/error states. A login link that cannot be used is not an
// error: it falls back to signing in with an emailed code, inline on
// /login-link. The retired /unsubscribe-login link only redirects to /account.
import {test, expect} from '../helpers/fixtures';
import {
  expectSignedInAs,
  loginResponse,
  mockAccountDashboard,
  mockEmailAuthFlow,
  mockEventRegistration,
  mockLoginCodeFlow,
  mockPastProjects,
  pastProjectRows,
  seedAuthenticatedSession,
} from '../helpers';

const SUCCESS = loginResponse({user: {email: 'token-login@example.com', member_uuid: 'm-token'}});

const UNUSABLE_LINK = "This sign-in link can't be used.";
const EXPIRED_LINK = 'This sign-in link has expired.';
const USED_LINK = 'This sign-in link has already been used.';
const CANT_VERIFY_LINK = "We couldn't verify your sign-in link right now.";
// The code step: the server's own (generic) acknowledgement, then a nudge for a mistyped address.
const CODE_ACK = 'If an eligible account exists, a verification code has been sent.';
const CODE_HINT = "Didn't get a code? Check the address above or go back to correct it.";

// The fallback is informational: none of the error markup may appear.
const ERROR_MARKUP = '.magic-login-error, .auth-alert.error';

interface TokenCase {
  name: string;
  path: string;
  endpoint: string;
  /** Login links fall back to an emailed code; other tokens keep their error text. */
  fallback: boolean;
  invalidText: string;
  noTokenText: string;
}

const cases: TokenCase[] = [
  {name: 'login-link', path: '/login-link', endpoint: '**/mail/login-link/', fallback: true, invalidText: UNUSABLE_LINK, noTokenText: UNUSABLE_LINK},
  // Legacy aliases from already-sent emails redirect into /login-link.
  {name: 'magic-alias', path: '/magic-login', endpoint: '**/mail/login-link/', fallback: true, invalidText: UNUSABLE_LINK, noTokenText: UNUSABLE_LINK},
  {name: 'ticket-alias', path: '/ticket-login', endpoint: '**/mail/login-link/', fallback: true, invalidText: UNUSABLE_LINK, noTokenText: UNUSABLE_LINK},
  {
    name: 'impersonate',
    path: '/impersonate-login',
    endpoint: '**/authn/impersonate-login/',
    fallback: false,
    invalidText: 'This impersonation link is invalid or has expired.',
    noTokenText: 'No impersonation token provided.',
  },
];

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

test('login-link that has expired signs the member in with an emailed code', async ({page}) => {
  const email = 'expired-link@example.com';
  // The existing-accounts code flow (/authn/login/*), never the unified
  // email-auth one, which would create an account for a mistyped address.
  const loginCode = await mockLoginCodeFlow(page, {
    verifyResponse: loginResponse({user: {email, member_uuid: 'm-expired'}}),
  });
  const unifiedFlowCalls: string[] = [];
  await page.route('**/authn/email-auth/**', (route) => {
    unifiedFlowCalls.push(route.request().url());
    return route.fulfill({status: 500, contentType: 'application/json', body: '{}'});
  });
  await mockAccountDashboard(page, {email});
  await page.route('**/mail/login-link/', (route) =>
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({detail: 'This login link has expired.', code: 'expired'}),
    }),
  );
  await page.goto('/login-link?token=old', {waitUntil: 'domcontentloaded'});

  // No error: a notice and the email step, on the same route.
  await expect(page.getByText(EXPIRED_LINK)).toBeVisible();
  await expect(page.locator(ERROR_MARKUP)).toHaveCount(0);
  await page.getByLabel('Email address').fill(email);
  await page.getByRole('button', {name: 'Send sign-in code'}).click();

  await expect(page.getByRole('heading', {name: 'Verify Login', level: 1})).toBeVisible();
  // Focus follows the visitor to the code field rather than dropping to <body>.
  const codeField = page.getByRole('textbox', {name: '6-digit verification code'});
  await expect(codeField).toBeFocused();
  // The server's acknowledgement and the hint are read with the focused field.
  await expect(page.getByText(CODE_ACK)).toBeVisible();
  await expect(page.getByText(CODE_HINT)).toBeVisible();
  await expect(codeField).toHaveAccessibleDescription(`${CODE_ACK} ${CODE_HINT}`);
  expect(loginCode.requestPayloads).toEqual([expect.objectContaining({email})]);
  await expect(page).toHaveURL(/\/login-link$/);

  await codeField.fill('123456');
  await page.getByRole('button', {name: 'Verify and Sign In'}).click();

  await expect(page).toHaveURL(/\/account$/);
  await expectSignedInAs(page, email);
  expect(loginCode.verifyPayloads).toEqual([{email, code: '123456'}]);
  expect(unifiedFlowCalls).toEqual([]);
});

test('login-link that has expired replaces another members stored session and lands on the link destination', async ({page}) => {
  const staleEmail = 'stale-member@example.com';
  const email = 'fresh-member@example.com';
  // Installed first: the seeded session then stays the authoritative one until
  // the code exchange succeeds and re-points it at the new member.
  const loginCode = await mockLoginCodeFlow(page, {
    verifyResponse: loginResponse({user: {email, member_uuid: 'm-fresh'}}),
  });
  await seedAuthenticatedSession(page, {user: {email: staleEmail, member_uuid: 'm-stale'}});
  await mockPastProjects(page, pastProjectRows());
  await page.route('**/mail/login-link/', (route) =>
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({detail: 'This login link has expired.', code: 'expired', redirect_to: '/past-projects'}),
    }),
  );
  await page.goto('/login-link?token=old', {waitUntil: 'domcontentloaded'});

  // The stale member is signed in, yet the visitor is not sent to /account.
  await expect(page.getByText(EXPIRED_LINK)).toBeVisible();
  await expect(page).toHaveURL(/\/login-link$/);
  await expectSignedInAs(page, staleEmail);

  await page.getByLabel('Email address').fill(email);
  await page.getByRole('button', {name: 'Send sign-in code'}).click();
  await page.getByRole('textbox', {name: '6-digit verification code'}).fill('123456');
  await page.getByRole('button', {name: 'Verify and Sign In'}).click();

  await expect(page).toHaveURL(/\/past-projects$/);
  await expectSignedInAs(page, email);
  await expect(page.locator('#menu-root')).not.toContainText(staleEmail);
  expect(loginCode.verifyPayloads).toEqual([{email, code: '123456'}]);
});

test('login-link already used, with a dead stored session, offers the emailed-code sign-in and lands on the link destination', async ({page}) => {
  const deadEmail = 'dead-session@example.com';
  const email = 'used-link@example.com';
  const loginCode = await mockLoginCodeFlow(page, {
    verifyResponse: loginResponse({user: {email, member_uuid: 'm-used'}}),
  });
  await mockPastProjects(page, pastProjectRows());
  // A session left behind by an account the server no longer accepts: both the
  // session check and the refresh are refused for it, and only for it.
  await page.addInitScript(
    ({key, user}) => {
      localStorage.setItem(
        key,
        JSON.stringify({
          version: 1,
          generation: 'e2e-dead-generation',
          access: 'dead-access-e2e',
          refresh: 'dead-refresh-e2e',
          user,
          requires_profile_completion: false,
        }),
      );
    },
    {key: 'i2g_auth_session', user: {email: deadEmail, member_uuid: 'm-dead'}},
  );
  await page.route('**/authn/session/', (route) =>
    route.request().headers()['authorization'] === 'Bearer dead-access-e2e'
      ? route.fulfill({status: 401, contentType: 'application/json', body: JSON.stringify({detail: 'User not found'})})
      : route.fallback(),
  );
  await page.route('**/authn/refresh/', (route) =>
    (route.request().postDataJSON() as {refresh?: string}).refresh === 'dead-refresh-e2e'
      ? route.fulfill({status: 401, contentType: 'application/json', body: JSON.stringify({detail: 'Token is invalid'})})
      : route.fallback(),
  );
  await page.route('**/mail/login-link/', (route) =>
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: 'This login link has already been used.',
        code: 'already_used',
        redirect_to: '/past-projects',
      }),
    }),
  );
  await page.goto('/login-link?token=used', {waitUntil: 'domcontentloaded'});

  // Not /account as an anonymous visitor, and not an error: the dead session is
  // dropped and the code sign-in is offered instead.
  await expect(page.getByText(USED_LINK)).toBeVisible();
  await expect(page).toHaveURL(/\/login-link$/);
  await expect(page.locator(ERROR_MARKUP)).toHaveCount(0);

  await page.getByLabel('Email address').fill(email);
  await page.getByRole('button', {name: 'Send sign-in code'}).click();
  await page.getByRole('textbox', {name: '6-digit verification code'}).fill('123456');
  await page.getByRole('button', {name: 'Verify and Sign In'}).click();

  await expect(page).toHaveURL(/\/past-projects$/);
  await expectSignedInAs(page, email);
  await expect(page.locator('#menu-root')).not.toContainText(deadEmail);
  expect(loginCode.verifyPayloads).toEqual([{email, code: '123456'}]);
});

test('login-link rate limit offers the email-code sign-in and a retry that signs the member in', async ({page}) => {
  await mockAccountDashboard(page, {email: SUCCESS.user.email});
  let attempts = 0;
  await page.route('**/mail/login-link/', (route) => {
    attempts += 1;
    if (attempts === 1) {
      return route.fulfill({
        status: 429,
        contentType: 'application/json',
        body: JSON.stringify({detail: 'Request was throttled.'}),
      });
    }
    return route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(SUCCESS)});
  });
  await page.goto('/login-link?token=busy', {waitUntil: 'domcontentloaded'});
  // Rate limited: still no error, the code sign-in is offered, and so is a retry.
  await expect(page.getByText(CANT_VERIFY_LINK)).toBeVisible();
  await expect(page.getByLabel('Email address')).toBeVisible();
  await expect(page.locator(ERROR_MARKUP)).toHaveCount(0);

  await page.getByRole('button', {name: 'Try the link again'}).click();
  await expectSignedInAs(page, SUCCESS.user.email);
  expect(attempts).toBe(2);
});

// /unsubscribe-login is retired: no email has produced it for months and every
// token it carried has expired. Old links land on the account page, where email
// preferences live, and the token never reaches a request.
const RETIRED_UNSUBSCRIBE_TOKEN = 'retired-unsubscribe-7c4e1a';
for (const tokenPart of [`#token=${RETIRED_UNSUBSCRIBE_TOKEN}`, `?token=${RETIRED_UNSUBSCRIBE_TOKEN}`]) {
  test(`retired unsubscribe-login link (${tokenPart[0]}token) redirects to /account without exchanging the token`, async ({page}) => {
    const email = 'legacy-unsubscribe@example.com';
    await seedAuthenticatedSession(page, {user: {email, member_uuid: 'm-legacy-unsubscribe'}});
    const leaked: string[] = [];
    page.on('request', (request) => {
      if (request.isNavigationRequest()) return;
      const url = request.url();
      // Skip the Referer: for ?token= the browser itself sends the page URL as
      // the same-origin Referer of the page's own asset and bootstrap requests.
      const headers = Object.entries(request.headers())
        .filter(([name]) => name.toLowerCase() !== 'referer')
        .map(([name, value]) => `${name}: ${value}`);
      const sent = [url, request.postData() ?? '', ...headers];
      if (url.includes('unsubscribe') || sent.some((part) => part.includes(RETIRED_UNSUBSCRIBE_TOKEN))) {
        leaked.push(`${request.method()} ${url}`);
      }
    });

    await page.goto(`/unsubscribe-login${tokenPart}`, {waitUntil: 'domcontentloaded'});

    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByRole('heading', {name: 'Account Dashboard', level: 1})).toBeVisible();
    await expectSignedInAs(page, email);
    expect(leaked).toEqual([]);
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

test('email-auth-link accepts fragment parameters', async ({page}) => {
  const email = 'fragment-auth@example.com';
  await mockAccountDashboard(page, {email});
  await page.route('**/authn/email-auth/verify-code/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(loginResponse({user: {email, member_uuid: 'm-fragment'}})),
    }),
  );
  await page.goto(
    `/email-auth-link#flow=auth&source=login&email=${encodeURIComponent(email)}&code=123456`,
    {waitUntil: 'domcontentloaded'},
  );

  await expect(page).toHaveURL(/\/account$/);
  expect(new URL(page.url()).hash).toBe('');
  await expectSignedInAs(page, email);
});

test('email-auth-link with malformed params shows the guard error', async ({page}) => {
  await page.goto('/email-auth-link?flow=auth&source=subscribe&email=x@example.com', {waitUntil: 'domcontentloaded'});
  await expect(page.getByText('This email link is invalid or incomplete.')).toBeVisible();
});

test('/membership/events legacy alias renders the event registration page', async ({page}) => {
  await mockEventRegistration(page);
  await mockEmailAuthFlow(page);
  await page.goto('/membership/events', {waitUntil: 'domcontentloaded'});
  // The legacy path renders EventRegistrationPage in place (no redirect hop),
  // so old emailed/bookmarked URLs keep working — see router.tsx.
  await expect(page).toHaveURL(/\/membership\/events/);
  await expect(page.getByRole('heading', {name: 'Event Registration', level: 1})).toBeVisible();
});

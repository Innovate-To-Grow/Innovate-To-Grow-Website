// Token login entry points POST a token, persist sessions where appropriate,
// and render success/error states. A login link that cannot be used is not an
// error: it falls back to signing in with an emailed code, inline on
// /login-link. The retired /unsubscribe-login link only redirects to /account.
import {test, expect} from '../../helpers/fixtures';
import {
  expectSignedInAs,
  loginResponse,
  mockAccountDashboard,
  mockLoginCodeFlow,
  mockPastProjects,
  pastProjectRows,
  seedAuthenticatedSession,
} from '../../helpers';
import {
  CODE_ACK,
  CODE_HINT,
  ERROR_MARKUP,
  EXPIRED_LINK,
  USED_LINK,
} from './tokenLoginFixtures';

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

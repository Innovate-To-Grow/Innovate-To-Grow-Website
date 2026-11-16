// Token login entry points POST a token, persist sessions where appropriate,
// and render success/error states. A login link that cannot be used is not an
// error: it falls back to signing in with an emailed code, inline on
// /login-link. The retired /unsubscribe-login link only redirects to /account.
import {test, expect} from '../../helpers/fixtures';
import {
  expectSignedInAs,
  loginResponse,
  mockAccountDashboard,
  mockEmailAuthFlow,
  mockEventRegistration,
} from '../../helpers';
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

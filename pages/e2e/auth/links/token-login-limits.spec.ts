// Token login entry points POST a token, persist sessions where appropriate,
// and render success/error states. A login link that cannot be used is not an
// error: it falls back to signing in with an emailed code, inline on
// /login-link. The retired /unsubscribe-login link only redirects to /account.
import {test, expect} from '../../helpers/fixtures';
import {
  expectSignedInAs,
  mockAccountDashboard,
  seedAuthenticatedSession,
} from '../../helpers';
import {
  CANT_VERIFY_LINK,
  ERROR_MARKUP,
  RETIRED_UNSUBSCRIBE_TOKEN,
  SUCCESS,
} from './tokenLoginFixtures';

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

// Email-code login journey + the verify-email route guards. Password login is
// intentionally not exercised here (RSA-OAEP fixture, duplicate of vitest).
import {test, expect} from './fixtures';
import {
  loginResponse,
  mockEmailAuthFlow,
  mockProfileEndpoint,
  profileResponse,
  seedAuthenticatedSession,
} from './helpers';

async function stubAccountMounts(page: import('@playwright/test').Page, email: string) {
  await mockProfileEndpoint(page, {current: profileResponse({email})});
  await page.route('**/event/my-tickets/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
  await page.route('**/event/registration-options/', (route) =>
    route.fulfill({status: 404, contentType: 'application/json', body: JSON.stringify({detail: 'none'})}),
  );
}

test('email-code login routes /login → verify → /account', {tag: '@core'}, async ({page}) => {
  const email = 'login-flow@example.com';
  const {requestPayloads} = await mockEmailAuthFlow(page, {
    verifyResponse: loginResponse({user: {email, member_uuid: 'm-login'}, next_step: 'account'}),
  });
  await stubAccountMounts(page, email);

  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', {name: /continue with email/i}).click();

  await expect(page).toHaveURL(
    new RegExp(`/verify-email\\?flow=auth&email=${encodeURIComponent(email).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`),
  );
  expect(requestPayloads).toEqual([{email, source: 'login'}]);

  await page.getByLabel('6-digit verification code').fill('123456');
  await page.getByRole('button', {name: 'Continue', exact: true}).click();

  await expect(page).toHaveURL(/\/account$/);
});

test('verify with requires_profile_completion routes to /complete-profile', async ({page}) => {
  const email = 'needs-profile@example.com';
  await mockEmailAuthFlow(page, {
    verifyResponse: loginResponse({
      user: {email, member_uuid: 'm-np'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
    }),
  });
  await mockProfileEndpoint(page, {current: profileResponse({email})});

  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', {name: /continue with email/i}).click();
  await page.getByLabel('6-digit verification code').fill('123456');
  await page.getByRole('button', {name: 'Continue', exact: true}).click();

  await expect(page).toHaveURL(/\/complete-profile$/);
});

test('verify-code error keeps the user on the verify screen', async ({page}) => {
  await mockEmailAuthFlow(page, {verifyStatus: 400});

  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.getByLabel('Email').fill('bad-code@example.com');
  await page.getByRole('button', {name: /continue with email/i}).click();
  await page.getByLabel('6-digit verification code').fill('000000');
  await page.getByRole('button', {name: 'Continue', exact: true}).click();

  await expect(page.locator('.auth-alert.error')).toBeVisible();
  await expect(page).toHaveURL(/\/verify-email\?flow=auth/);
});

test('/register redirects to /login', async ({page}) => {
  await page.goto('/register', {waitUntil: 'domcontentloaded'});
  await expect(page).toHaveURL(/\/login$/);
});

test('verify-email with no flow/email redirects to /login', async ({page}) => {
  await page.goto('/verify-email', {waitUntil: 'domcontentloaded'});
  await expect(page).toHaveURL(/\/login$/);
});

test('verify-email flow=change while logged out redirects to /login', async ({page}) => {
  await page.goto('/verify-email?flow=change&email=x@example.com', {waitUntil: 'domcontentloaded'});
  await expect(page).toHaveURL(/\/login$/);
});

test('/login while authenticated redirects to /account', async ({page}) => {
  await seedAuthenticatedSession(page, {user: {email: 'already-in@example.com'}});
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await expect(page).toHaveURL(/\/account$/);
});

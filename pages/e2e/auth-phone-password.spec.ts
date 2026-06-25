// Regression: a phone-only account can sign in with phone + password and set a
// password through SMS verification from the account page. The email-becomes-
// primary and email-deletion rules are covered by unit/integration tests; this
// spec exercises the cross-page UI path for the headline new capabilities.
import {test, expect} from './fixtures';
import {loginResponse, mockProfileEndpoint, mockPublicKey, profileResponse} from './helpers';

const PHONE = '2025550123';
const PHONE_E164 = '+12025550123';

function json(body: unknown, status = 200) {
  return {status, contentType: 'application/json', body: JSON.stringify(body)};
}

async function stubAccountSideEffects(page: import('@playwright/test').Page) {
  // Phone-only account: no primary email yet.
  await mockProfileEndpoint(page, {current: profileResponse({email: '', primary_email_id: null, email_verified: false})});
  await page.route('**/event/my-tickets/', (route) => route.fulfill(json([])));
  await page.route('**/event/registration-options/', (route) => route.fulfill(json({detail: 'none'}, 404)));
  await page.route('**/authn/account-emails/', (route) => route.fulfill(json({emails: []})));
  await page.route('**/authn/contact-emails/', (route) => route.fulfill(json([])));
  await page.route('**/authn/contact-phones/', (route) =>
    route.fulfill(json([{id: 'p-1', phone_number: PHONE, region: '1-US', region_display: 'United States', subscribe: false, verified: true, created_at: '2026-01-01T00:00:00Z'}])),
  );
}

test('phone account signs in with phone+password and sets a password via SMS', {tag: '@core'}, async ({page}) => {
  await mockPublicKey(page);

  const loginPayloads: unknown[] = [];
  await page.route('**/authn/login/', async (route) => {
    loginPayloads.push(route.request().postDataJSON());
    await route.fulfill(json(loginResponse({user: {email: '', phone: PHONE_E164, member_uuid: 'm-phone'}, next_step: 'account'})));
  });

  await stubAccountSideEffects(page);

  // Channel-aware change-password flow over SMS.
  await page.route('**/authn/change-password/request-code/', (route) =>
    route.fulfill(json({message: 'We texted a code to (•••) •••-0123.', channel: 'sms', destination: '(•••) •••-0123'})),
  );
  await page.route('**/authn/change-password/verify-code/', (route) =>
    route.fulfill(json({message: 'Verification code accepted.', verification_token: 'sms-token', channel: 'sms'})),
  );
  await page.route('**/authn/change-password/confirm/', (route) =>
    route.fulfill(json({message: 'Password changed successfully.'})),
  );

  // --- Sign in with phone number + password ---
  const main = page.locator('#root');
  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await main.getByRole('button', {name: 'Sign in with password instead'}).click();
  await page.getByLabel('Email or Phone').fill(PHONE);
  await page.getByLabel('Password').fill('PhonePass123!');
  await main.getByRole('button', {name: 'Sign In', exact: true}).click();

  await expect(page).toHaveURL(/\/account/);
  // The identifier was sent in the (backward-compatible) email field.
  expect(loginPayloads).toHaveLength(1);
  expect((loginPayloads[0] as {email?: string}).email).toBe(PHONE);

  // --- Set a password via SMS from the account page ---
  await main.getByRole('button', {name: 'Send Code'}).click();
  await expect(page.getByText('We texted a code to (•••) •••-0123.')).toBeVisible();

  await page.getByLabel('6-digit verification code').fill('123456');
  await main.getByRole('button', {name: 'Verify Code'}).click();

  await page.getByLabel('New Password').fill('BrandNewPass123!');
  await page.getByLabel('Confirm Password').fill('BrandNewPass123!');
  await main.getByRole('button', {name: 'Change Password'}).click();

  await expect(page.getByText('Password changed successfully.')).toBeVisible();
});

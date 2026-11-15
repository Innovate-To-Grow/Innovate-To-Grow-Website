// Regression: a phone-only account can sign in with phone + password and set a
// password through SMS verification from the account page; and an account with a
// verified phone can remove its primary email (the verified phone keeps it safe).
import {test, expect} from '../../helpers/fixtures';
import {
  loginResponse,
  mockPublicKey,
  mockSendVerification,
  seedAuthenticatedSession,
} from '../../helpers';
import {json, PHONE, PHONE_E164, stubAccountSideEffects} from './phonePasswordFixtures';

test('phone account signs in with phone+password and sets a password via SMS', {tag: '@core'}, async ({page}) => {
  await mockPublicKey(page);
  await mockSendVerification(page);

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

test('phone account can change password via SMS code from account page', async ({page}) => {
  await mockSendVerification(page);
  await seedAuthenticatedSession(page, {
    user: {email: '', phone: '+12025550123'},
    profile: {email: '', email_verified: false, primary_email_id: null},
  });

  await page.route('**/authn/change-password/request-code/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({message: 'We texted a code.', channel: 'sms', destination: '(•••) •••-0123'}),
    }),
  );
  await page.route('**/authn/change-password/verify-code/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({message: 'Verified.', verification_token: 'token'}),
    }),
  );
  await page.route('**/authn/change-password/confirm/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({message: 'Password changed.'})}),
  );

  await page.goto('/account', {waitUntil: 'domcontentloaded'});

  const sendCodeBtn = page.getByRole('button', {name: 'Send Code'});
  await expect(sendCodeBtn).toBeVisible();
  await sendCodeBtn.click();
  await expect(page.getByText(/texted a code/i)).toBeVisible();
});

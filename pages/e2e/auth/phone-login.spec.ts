// SMS-code journey through the unified login field + the verify-phone route
// guards. Twin of auth-login.spec.ts (which covers the email branch). The smart
// "Email or phone number" field detects a US number and routes to /verify-phone;
// a new number registers, an existing one logs in — both passwordless.
import {test, expect} from './fixtures';
import {loginResponse, mockAccountDashboard, mockPhoneAuthFlow, mockProfileEndpoint, profileResponse} from './helpers';

const PHONE_INPUT = '2025550123';
const PHONE_E164 = '+12025550123';

test('phone-code login: unified field routes /login → verify-phone → /account', {tag: '@core'}, async ({page}) => {
  const {requestPayloads, verifyPayloads} = await mockPhoneAuthFlow(page, {
    verifyResponse: loginResponse({
      user: {email: '', phone: PHONE_E164, member_uuid: 'm-phone'},
      next_step: 'account',
    }),
  });
  await mockAccountDashboard(page);

  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.getByLabel('Email or phone number').fill(PHONE_INPUT);
  await page.getByRole('button', {name: 'Continue', exact: true}).click();

  await expect(page).toHaveURL(/\/verify-phone\?phone=2025550123/);
  expect(requestPayloads).toEqual([{phone_number: PHONE_INPUT, region: '1-US', source: 'login'}]);

  await page.getByLabel('6-digit verification code').fill('654321');
  await page.getByRole('button', {name: 'Verify', exact: true}).click();

  await expect(page).toHaveURL(/\/account$/);
  expect(verifyPayloads).toEqual([{phone_number: PHONE_INPUT, region: '1-US', code: '654321'}]);
});

test('phone-code register: a new number routes to /complete-profile', async ({page}) => {
  await mockPhoneAuthFlow(page, {
    verifyResponse: loginResponse({
      user: {email: '', phone: PHONE_E164, member_uuid: 'm-new'},
      next_step: 'complete_profile',
      requires_profile_completion: true,
    }),
  });
  // Phone-only new account: profile has no email yet and an empty name, so the
  // complete-profile step keeps the user there.
  await mockProfileEndpoint(page, {current: profileResponse({email: ''})});

  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.getByLabel('Email or phone number').fill(PHONE_INPUT);
  await page.getByRole('button', {name: 'Continue', exact: true}).click();
  await page.getByLabel('6-digit verification code').fill('654321');
  await page.getByRole('button', {name: 'Verify', exact: true}).click();

  await expect(page).toHaveURL(/\/complete-profile$/);
});

test('phone verify-code error keeps the user on the verify screen', async ({page}) => {
  await mockPhoneAuthFlow(page, {verifyStatus: 400});

  await page.goto('/login', {waitUntil: 'domcontentloaded'});
  await page.getByLabel('Email or phone number').fill(PHONE_INPUT);
  await page.getByRole('button', {name: 'Continue', exact: true}).click();
  await page.getByLabel('6-digit verification code').fill('000000');
  await page.getByRole('button', {name: 'Verify', exact: true}).click();

  await expect(page.locator('.auth-alert.error')).toBeVisible();
  await expect(page).toHaveURL(/\/verify-phone\?phone=2025550123/);
});

test('phone login carries a safe returnTo into the verify-phone URL', async ({page}) => {
  await mockPhoneAuthFlow(page);

  await page.goto('/login?returnTo=%2Fpast-projects', {waitUntil: 'domcontentloaded'});
  await page.getByLabel('Email or phone number').fill(PHONE_INPUT);
  await page.getByRole('button', {name: 'Continue', exact: true}).click();

  await expect(page).toHaveURL(/\/verify-phone\?phone=2025550123&returnTo=%2Fpast-projects/);
});

test('verify-phone resend re-requests an SMS code', async ({page}) => {
  const {requestPayloads} = await mockPhoneAuthFlow(page);

  await page.goto(`/verify-phone?phone=${PHONE_INPUT}`, {waitUntil: 'domcontentloaded'});
  await page.getByRole('button', {name: 'Resend code'}).last().click();

  await expect.poll(() => requestPayloads.length).toBeGreaterThan(0);
  expect(requestPayloads.at(-1)).toEqual({phone_number: PHONE_INPUT, region: '1-US', source: 'login'});
});

test('verify-phone with an invalid phone param redirects to /login', async ({page}) => {
  await page.goto('/verify-phone?phone=123', {waitUntil: 'domcontentloaded'});
  await expect(page).toHaveURL(/\/login$/);
});

test('verify-phone with no phone param redirects to /login', async ({page}) => {
  await page.goto('/verify-phone', {waitUntil: 'domcontentloaded'});
  await expect(page).toHaveURL(/\/login$/);
});

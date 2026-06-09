// Forgot-password journey, driven all the way through the encrypted confirm
// step. `mockPublicKey` serves a real RSA key so the browser's Web Crypto can
// encrypt; the confirm mock asserts the request body shape, not the plaintext.
import {test, expect} from './fixtures';
import {mockPasswordResetFlow, mockPublicKey} from './helpers';

test('request → verify → set new password → /login', {tag: '@core'}, async ({page}) => {
  await mockPublicKey(page);
  const {requestPayloads, verifyPayloads, confirmPayloads} = await mockPasswordResetFlow(page, {
    verifyToken: 'reset-token-e2e',
  });
  const email = 'reset@example.com';

  await page.goto('/forgot-password', {waitUntil: 'domcontentloaded'});
  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', {name: 'Send Reset Code'}).click();

  await expect(page).toHaveURL(/\/verify-email\?flow=reset&email=reset%40example\.com/);
  await expect(page.getByRole('heading', {name: 'Reset Password'})).toBeVisible();
  expect(requestPayloads).toEqual([{email}]);

  await page.getByLabel('6-digit verification code').fill('654321');
  await page.getByRole('button', {name: 'Verify Code'}).click();

  await expect(page.getByText('Code verified. Set your new password below.')).toBeVisible();
  expect(verifyPayloads).toEqual([{email, code: '654321'}]);

  await page.getByLabel('New Password').fill('NewPassw0rd!');
  await page.getByLabel('Confirm Password').fill('NewPassw0rd!');
  await page.getByRole('button', {name: 'Reset Password'}).click();

  await expect(page.getByText('Password reset successful.')).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);

  expect(confirmPayloads).toHaveLength(1);
  const confirm = confirmPayloads[0] as Record<string, unknown>;
  expect(confirm).toMatchObject({email, verification_token: 'reset-token-e2e', key_id: 'e2e-key'});
  expect(typeof confirm.new_password).toBe('string');
  expect(typeof confirm.new_password_confirm).toBe('string');
});

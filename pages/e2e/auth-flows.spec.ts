import {expect, test} from '@playwright/test';
import {mockHealthyAppShell} from './helpers';
import type {ProfileResponse} from '../src/features/auth/api/types';

const subscriberProfile = (overrides: Partial<ProfileResponse> = {}): ProfileResponse => ({
  member_uuid: 'member-e2e-1',
  email: 'subscriber@example.com',
  email_verified: true,
  primary_email_id: 'email-e2e-1',
  first_name: '',
  middle_name: '',
  last_name: '',
  organization: '',
  title: '',
  email_subscribe: false,
  is_staff: false,
  is_active: true,
  date_joined: '2026-01-01T00:00:00Z',
  ...overrides,
});

test('newsletter email-code flow completes profile and manages subscription', async ({page}) => {
  await mockHealthyAppShell(page);

  const requestCodePayloads: unknown[] = [];
  const verifyCodePayloads: unknown[] = [];
  const profilePatchPayloads: unknown[] = [];
  let profile = subscriberProfile();

  await page.route('**/authn/email-auth/request-code/', async (route) => {
    requestCodePayloads.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({message: 'Verification code sent.'}),
    });
  });

  await page.route('**/authn/email-auth/verify-code/', async (route) => {
    verifyCodePayloads.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: 'Login successful.',
        access: 'access-token',
        refresh: 'refresh-token',
        user: {member_uuid: profile.member_uuid, email: profile.email},
        next_step: 'complete_profile',
        requires_profile_completion: true,
      }),
    });
  });

  await page.route('**/authn/profile/', async (route) => {
    const request = route.request();

    if (request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(profile),
      });
      return;
    }

    if (request.method() === 'PATCH') {
      const payload = request.postDataJSON() as Partial<ProfileResponse>;
      profilePatchPayloads.push(payload);
      profile = {...profile, ...payload};
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(profile),
      });
      return;
    }

    await route.fulfill({status: 405});
  });

  await page.goto('/subscribe', {waitUntil: 'domcontentloaded'});

  await page.getByLabel('Email').fill('subscriber@example.com');
  await page.getByRole('button', {name: /continue with email/i}).click();
  await expect(page.getByLabel('Verification Code')).toBeVisible();
  expect(requestCodePayloads).toEqual([{email: 'subscriber@example.com', source: 'subscribe'}]);

  await page.getByLabel('Verification Code').fill('123456');
  await page.getByRole('button', {name: 'Verify Code'}).click();
  await expect(page.getByLabel(/first name/i)).toBeVisible();
  expect(verifyCodePayloads).toEqual([{email: 'subscriber@example.com', code: '123456'}]);

  await page.getByLabel(/first name/i).fill('Ada');
  await page.getByLabel(/last name/i).fill('Lovelace');
  await page.getByPlaceholder('Company or organization name').fill('Acme Corp');
  await page.getByPlaceholder('Your title or position (e.g. CEO, Director)').fill('Director');
  await page.getByRole('button', {name: 'Continue'}).click();

  await expect(page.getByText('Manage your email subscription preferences below.')).toBeVisible();
  await expect(page.getByText('subscriber@example.com')).toBeVisible();
  expect(profilePatchPayloads[0]).toEqual({
    first_name: 'Ada',
    middle_name: '',
    last_name: 'Lovelace',
    organization: 'Acme Corp',
    title: 'Director',
    email_subscribe: true,
  });

  await page.getByRole('button', {name: 'Turn off newsletter subscription'}).click();
  await expect(page.getByText('You have been unsubscribed from updates and announcements.')).toBeVisible();
  expect(profilePatchPayloads[1]).toEqual({email_subscribe: false});
});

test('forgot password flow verifies reset code before password entry', async ({page}) => {
  await mockHealthyAppShell(page);

  const resetRequestPayloads: unknown[] = [];
  const resetVerifyPayloads: unknown[] = [];

  await page.route('**/authn/password-reset/request-code/', async (route) => {
    resetRequestPayloads.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({message: 'Reset code sent.'}),
    });
  });

  await page.route('**/authn/password-reset/verify-code/', async (route) => {
    resetVerifyPayloads.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: 'Code verified.',
        verification_token: 'reset-token-e2e',
      }),
    });
  });

  await page.goto('/forgot-password', {waitUntil: 'domcontentloaded'});

  await page.getByLabel('Email').fill('reset@example.com');
  await page.getByRole('button', {name: 'Send Reset Code'}).click();

  await expect(page).toHaveURL(/\/verify-email\?flow=reset&email=reset%40example\.com/);
  await expect(page.getByRole('heading', {name: 'Reset Password'})).toBeVisible();
  expect(resetRequestPayloads).toEqual([{email: 'reset@example.com'}]);

  await page.getByLabel('6-digit verification code').fill('654321');
  await page.getByRole('button', {name: 'Verify Code'}).click();

  await expect(page.getByText('Code verified. Set your new password below.')).toBeVisible();
  await expect(page.getByLabel('New Password')).toBeVisible();
  await expect(page.getByLabel('Confirm Password')).toBeVisible();
  expect(resetVerifyPayloads).toEqual([{email: 'reset@example.com', code: '654321'}]);
});

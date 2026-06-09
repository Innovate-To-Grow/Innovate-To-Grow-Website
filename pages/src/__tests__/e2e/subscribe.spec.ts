// /subscribe end-to-end: email-code → inline profile completion → subscription
// management → unsubscribe. Migrated from the original auth-flows.spec.ts and
// rebuilt on the shared fixtures + factories.
import {test, expect} from './fixtures';
import {mockEmailAuthFlow, mockProfileEndpoint, profileResponse} from './helpers';

test('newsletter email-code flow completes profile and manages subscription', {tag: '@core'}, async ({page}) => {
  const email = 'subscriber@example.com';
  const profileRef = {current: profileResponse({email, member_uuid: 'member-e2e-1', primary_email_id: 'email-e2e-1'})};

  const {requestPayloads, verifyPayloads} = await mockEmailAuthFlow(page, {
    verifyResponse: {
      message: 'Login successful.',
      access: 'access-token',
      refresh: 'refresh-token',
      user: {member_uuid: profileRef.current.member_uuid, email},
      next_step: 'complete_profile',
      requires_profile_completion: true,
    },
  });
  const patchPayloads = await mockProfileEndpoint(page, profileRef);

  await page.goto('/subscribe', {waitUntil: 'domcontentloaded'});

  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', {name: /continue with email/i}).click();
  await expect(page.getByLabel('Verification Code')).toBeVisible();
  expect(requestPayloads).toEqual([{email, source: 'subscribe'}]);

  await page.getByLabel('Verification Code').fill('123456');
  await page.getByRole('button', {name: 'Verify Code'}).click();
  await expect(page.getByLabel(/first name/i)).toBeVisible();
  expect(verifyPayloads).toEqual([{email, code: '123456'}]);

  await page.getByLabel(/first name/i).fill('Ada');
  await page.getByLabel(/last name/i).fill('Lovelace');
  await page.getByPlaceholder('Company or organization name').fill('Acme Corp');
  await page.getByPlaceholder('Your title or position (e.g. CEO, Director)').fill('Director');
  await page.getByRole('button', {name: 'Continue'}).click();

  await expect(page.getByText('Manage your email subscription preferences below.')).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();
  expect(patchPayloads[0]).toEqual({
    first_name: 'Ada',
    middle_name: '',
    last_name: 'Lovelace',
    organization: 'Acme Corp',
    title: 'Director',
    email_subscribe: true,
  });

  await page.getByRole('button', {name: 'Turn off newsletter subscription'}).click();
  await expect(page.getByText('You have been unsubscribed from updates and announcements.')).toBeVisible();
  expect(patchPayloads[1]).toEqual({email_subscribe: false});
});

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
  const contactEmails = [{
    id: 'contact-email-e2e-1',
    email_address: 'secondary@example.com',
    email_type: 'secondary',
    subscribe: false,
    verified: true,
    created_at: '2026-01-02T00:00:00Z',
  }];
  const contactPhones = [{
    id: 'contact-phone-e2e-1',
    phone_number: '+14155550132',
    region: '1-US',
    region_display: 'United States',
    subscribe: true,
    verified: true,
    created_at: '2026-01-03T00:00:00Z',
  }];
  const contactEmailPatchPayloads: unknown[] = [];
  const contactPhonePatchPayloads: unknown[] = [];

  await page.route('**/authn/contact-emails/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(contactEmails)}),
  );
  await page.route('**/authn/contact-emails/contact-email-e2e-1/', async (route) => {
    const payload = route.request().postDataJSON();
    contactEmailPatchPayloads.push(payload);
    contactEmails[0] = {...contactEmails[0], ...(payload as Partial<typeof contactEmails[number]>)};
    await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(contactEmails[0])});
  });
  await page.route('**/authn/contact-phones/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(contactPhones)}),
  );
  await page.route('**/authn/contact-phones/contact-phone-e2e-1/', async (route) => {
    const payload = route.request().postDataJSON();
    contactPhonePatchPayloads.push(payload);
    contactPhones[0] = {...contactPhones[0], ...(payload as Partial<typeof contactPhones[number]>)};
    await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(contactPhones[0])});
  });

  await page.goto('/subscribe', {waitUntil: 'domcontentloaded'});

  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', {name: 'Continue', exact: true}).click();
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

  await expect(page.getByText('Manage your email and text message subscription preferences below.')).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();
  await expect(page.getByText('secondary@example.com')).toBeVisible();
  await expect(page.getByText('(415)555-0132')).toBeVisible();
  expect(patchPayloads[0]).toEqual({
    first_name: 'Ada',
    middle_name: '',
    last_name: 'Lovelace',
    organization: 'Acme Corp',
    title: 'Director',
    email_subscribe: true,
  });

  await page.getByRole('button', {name: 'Turn off newsletter subscription'}).click();
  await expect(page.getByText('Newsletters disabled.')).toBeVisible();
  expect(patchPayloads[1]).toEqual({email_subscribe: false});

  await page.getByRole('button', {name: 'Turn on newsletter subscription for secondary@example.com'}).click();
  await expect(page.getByText('Newsletters enabled.')).toBeVisible();
  expect(contactEmailPatchPayloads[0]).toEqual({subscribe: true});

  await page.getByRole('button', {name: 'Turn off text messages for (415)555-0132'}).click();
  await expect(page.getByText('Text Messages disabled.')).toBeVisible();
  expect(contactPhonePatchPayloads[0]).toEqual({subscribe: false});
});

// Event registration: the unauthenticated email step, a full completion to the
// ticket confirmation, and the already-registered short-circuit.
import {test, expect} from '../helpers/fixtures';
import {
  mockEventRegistration,
  registrationOptions,
  seedAuthenticatedSession,
} from '../helpers';

const contactOptions = (overrides: Parameters<typeof registrationOptions>[0] = {}) => registrationOptions({
  collect_phone: true,
  allow_secondary_email: true,
  member_emails: ['member@example.com'],
  member_profile: {first_name: 'Ada', middle_name: '', last_name: 'Lovelace', organization: 'Individual', title: ''},
  ...overrides,
});

test('verifies both required contacts and submits their event-scoped receipts', {tag: '@core'}, async ({page}) => {
  await seedAuthenticatedSession(page, {mockDashboardSideEffects: false});
  const mocked = await mockEventRegistration(page, {
    options: contactOptions({require_phone: true, verify_phone: true, require_secondary_email: true, verify_secondary_email: true}),
  });
  const accountContactWrites: string[] = [];
  page.on('request', (request) => {
    if (/\/authn\/contact-(emails|phones)\//.test(request.url()) && request.method() !== 'GET') accountContactWrites.push(request.url());
  });
  await page.goto('/event-registration', {waitUntil: 'domcontentloaded'});
  await page.locator('.event-reg-ticket-option').first().click();
  await page.getByRole('button', {name: 'Register', exact: true}).click();
  await expect(page.getByText('Phone number is required.', {exact: true})).toBeVisible();
  await expect(page.getByText('Secondary email is required.', {exact: true})).toBeVisible();

  await page.locator('#phone').fill('2025550123');
  await page.locator('#secondary-email').fill('personal@example.com');
  await page.getByRole('button', {name: 'Send phone code', exact: true}).click();
  await page.getByLabel('Phone verification code', {exact: true}).fill('123456');
  await page.getByRole('button', {name: 'Verify phone', exact: true}).click();
  await page.getByRole('button', {name: 'Send secondary email code', exact: true}).click();
  await page.getByLabel('Secondary email verification code', {exact: true}).fill('123456');
  await page.getByRole('button', {name: 'Verify secondary email', exact: true}).click();
  await expect(page.getByText('Verified', {exact: true})).toHaveCount(2);
  expect(accountContactWrites).toEqual([]);
  expect(mocked.created).toHaveLength(0);
  await page.getByRole('button', {name: 'Register', exact: true}).click();
  await expect(page.getByRole('heading', {name: "You're Registered!"})).toBeVisible();
  expect(mocked.created).toEqual([expect.objectContaining({
    attendee_phone: '2025550123', phone_verification_challenge_id: 'phone-challenge-e2e',
    attendee_secondary_email: 'personal@example.com',
    secondary_email_verification_challenge_id: 'email-challenge-e2e', secondary_email_verification_token: 'email-proof-e2e',
  })]);
  expect(mocked.phoneVerifications).toEqual([expect.objectContaining({event_slug: 'e2e-showcase', challenge_id: 'phone-challenge-e2e'})]);
  expect(mocked.secondaryEmailVerifications).toEqual([expect.objectContaining({event_slug: 'e2e-showcase', email: 'personal@example.com', challenge_id: 'email-challenge-e2e'})]);
});

test('allows blank optional contacts while requiring verification for supplied contacts', async ({page}) => {
  await seedAuthenticatedSession(page, {mockDashboardSideEffects: false});
  const mocked = await mockEventRegistration(page, {options: contactOptions({verify_phone: true, verify_secondary_email: true})});
  await page.goto('/event-registration', {waitUntil: 'domcontentloaded'});
  await page.locator('.event-reg-ticket-option').first().click();
  await page.locator('#phone').fill('2025550123');
  await page.locator('#secondary-email').fill('personal@example.com');
  await page.getByRole('button', {name: 'Register', exact: true}).click();
  await expect(page.getByText('Phone number must be verified.', {exact: true})).toBeVisible();
  await expect(page.getByText('Secondary email must be verified.', {exact: true})).toBeVisible();
  expect(mocked.created).toHaveLength(0);
  await page.locator('#phone').focus();
  await expect(page.locator('#phone')).toHaveValue('2025550123');
  await page.locator('#phone').fill('');
  await expect(page.locator('#phone')).toHaveValue('');
  await page.locator('#secondary-email').fill('');
  await page.getByRole('button', {name: 'Register', exact: true}).click();
  await expect(page.getByRole('heading', {name: "You're Registered!"})).toBeVisible();
  expect(mocked.created).toHaveLength(1);
  expect(mocked.created[0]).not.toHaveProperty('attendee_phone');
  expect(mocked.created[0]).not.toHaveProperty('attendee_secondary_email');
  expect(mocked.secondaryEmailCodeRequests).toHaveLength(0);
  expect(mocked.phoneCodeRequests).toHaveLength(0);
});

test('requires contact entry independently of verification', async ({page}) => {
  await seedAuthenticatedSession(page, {mockDashboardSideEffects: false});
  const mocked = await mockEventRegistration(page, {options: contactOptions({require_phone: true, require_secondary_email: true})});
  await page.goto('/event-registration', {waitUntil: 'domcontentloaded'});
  await page.locator('.event-reg-ticket-option').first().click();
  await page.getByRole('button', {name: 'Register', exact: true}).click();
  await expect(page.getByText('Phone number is required.', {exact: true})).toBeVisible();
  await expect(page.getByText('Secondary email is required.', {exact: true})).toBeVisible();
  await page.locator('#phone').fill('2025550123');
  await page.locator('#secondary-email').fill('personal@example.com');
  await expect(page.getByRole('button', {name: /Send .* code/})).toHaveCount(0);
  await page.getByRole('button', {name: 'Register', exact: true}).click();
  await expect(page.getByRole('heading', {name: "You're Registered!"})).toBeVisible();
  expect(mocked.created).toEqual([expect.objectContaining({attendee_phone: '2025550123', attendee_secondary_email: 'personal@example.com'})]);
  expect(mocked.created[0]).not.toHaveProperty('phone_verification_challenge_id');
  expect(mocked.created[0]).not.toHaveProperty('secondary_email_verification_token');
});

test('recognizes verified profile contacts and invalidates verification after editing', async ({page}) => {
  await seedAuthenticatedSession(page, {mockDashboardSideEffects: false});
  const mocked = await mockEventRegistration(page, {options: contactOptions({
    verify_phone: true, verify_secondary_email: true,
    member_phone: {phone_number: '+12025550123', region: '1-US', verified: true},
    member_secondary_email: {email_address: 'personal@example.com', verified: true},
  })});
  await page.goto('/event-registration', {waitUntil: 'domcontentloaded'});
  await expect(page.getByText('Verified', {exact: true})).toHaveCount(2);
  await page.locator('#secondary-email').fill('different@example.com');
  await expect(page.getByText('Verified', {exact: true})).toHaveCount(1);
  await page.locator('.event-reg-ticket-option').first().click();
  await page.getByRole('button', {name: 'Register', exact: true}).click();
  await expect(page.getByText('Secondary email must be verified.', {exact: true})).toBeVisible();
  expect(mocked.created).toHaveLength(0);
  await page.getByRole('button', {name: 'Send secondary email code', exact: true}).click();
  await page.getByLabel('Secondary email verification code', {exact: true}).fill('123456');
  await page.getByRole('button', {name: 'Verify secondary email', exact: true}).click();
  await expect(page.getByText('Verified', {exact: true})).toHaveCount(2);
  await page.getByRole('button', {name: 'Register', exact: true}).click();
  await expect(page.getByRole('heading', {name: "You're Registered!"})).toBeVisible();
  expect(mocked.phoneCodeRequests).toHaveLength(0);
  expect(mocked.created).toEqual([expect.objectContaining({attendee_secondary_email: 'different@example.com', secondary_email_verification_token: 'email-proof-e2e'})]);
});

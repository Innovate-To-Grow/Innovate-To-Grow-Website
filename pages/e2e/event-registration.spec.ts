// Event registration: the unauthenticated email step, a full completion to the
// ticket confirmation, and the already-registered short-circuit.
import {test, expect} from './fixtures';
import {
  loginResponse,
  mockEmailAuthFlow,
  mockEventRegistration,
  mockProfileEndpoint,
  profileResponse,
  registration,
  registrationOptions,
  seedAuthenticatedSession,
} from './helpers';

test('unauthenticated start shows the email step', async ({page}) => {
  await mockEventRegistration(page);
  await mockEmailAuthFlow(page);

  await page.goto('/event-registration', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Event Registration'})).toBeVisible();

  await page.getByLabel('Email').fill('reg@example.com');
  await page.getByRole('button', {name: /continue with email/i}).click();
  await expect(page.getByLabel('Verification Code')).toBeVisible();
});

test('completes a registration to the ticket confirmation', {tag: '@core'}, async ({page}) => {
  const email = 'reg-complete@example.com';
  const {created} = await mockEventRegistration(page);
  await mockEmailAuthFlow(page, {verifyResponse: loginResponse({user: {email}, next_step: 'account'})});
  await mockProfileEndpoint(page, {current: profileResponse({email})});

  await page.goto('/event-registration', {waitUntil: 'domcontentloaded'});

  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', {name: /continue with email/i}).click();
  await page.getByLabel('Verification Code').fill('123456');
  await page.getByRole('button', {name: 'Verify Code'}).click();

  // Registration form
  await page.locator('#first-name').fill('Ada');
  await page.locator('#last-name').fill('Lovelace');
  await page.locator('#attendee-organization').fill('Acme Corp');
  await page.locator('.event-reg-ticket-option').first().click();
  await page.getByRole('button', {name: 'Register'}).click();

  await expect(page.getByRole('heading', {name: "You're Registered!"})).toBeVisible();
  await expect(page.getByText('E2E-TICKET-001')).toBeVisible();
  await expect(page.getByRole('img', {name: 'Ticket barcode'})).toBeVisible();
  expect(created).toHaveLength(1);
});

test('already-registered member sees the confirmation immediately', async ({page}) => {
  await seedAuthenticatedSession(page, {mockDashboardSideEffects: false, user: {email: 'has-ticket@example.com'}});
  await mockEventRegistration(page, {options: registrationOptions({registration: registration()})});

  await page.goto('/event-registration', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: "You're Registered!"})).toBeVisible();
  await expect(page.getByText('E2E-TICKET-001')).toBeVisible();
});

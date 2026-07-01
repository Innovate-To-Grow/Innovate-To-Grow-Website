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
  registrationEvent,
  registrationOptions,
  seedAuthenticatedSession,
} from './helpers';

test('unauthenticated start shows the email step', async ({page}) => {
  await mockEventRegistration(page);
  await mockEmailAuthFlow(page);

  await page.goto('/event-registration', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Event Registration'})).toBeVisible();

  await page.getByLabel('Email').fill('reg@example.com');
  await page.getByRole('button', {name: 'Continue', exact: true}).click();
  await expect(page.getByLabel('Verification Code')).toBeVisible();
});

test('completes a registration to the ticket confirmation', {tag: '@core'}, async ({page}) => {
  const email = 'reg-complete@example.com';
  const {created} = await mockEventRegistration(page);
  await mockEmailAuthFlow(page, {verifyResponse: loginResponse({user: {email}, next_step: 'account'})});
  await mockProfileEndpoint(page, {current: profileResponse({email})});

  await page.goto('/event-registration', {waitUntil: 'domcontentloaded'});

  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', {name: 'Continue', exact: true}).click();
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

test('selects one of multiple open events and completes registration', async ({page}) => {
  const email = 'multi-event@example.com';
  const fallOptions = registrationOptions({
    id: 'event-fall',
    name: 'Fall Showcase',
    slug: 'fall-showcase',
    date: '2026-10-01',
    location: 'Conference Center',
    description: 'Fall registration event.',
    tickets: [{id: 'ticket-fall', name: 'Fall General Admission'}],
  });
  const {created} = await mockEventRegistration(page, {
    events: [
      registrationEvent({id: 'event-spring', name: 'Spring Showcase', slug: 'spring-showcase', date: '2026-05-01'}),
      registrationEvent({
        id: 'event-fall',
        name: 'Fall Showcase',
        slug: 'fall-showcase',
        date: '2026-10-01',
        location: 'Conference Center',
      }),
    ],
    options: fallOptions,
    registration: registration({
      event: {
        id: 'event-fall',
        name: 'Fall Showcase',
        slug: 'fall-showcase',
        date: '2026-10-01',
        location: 'Conference Center',
        description: 'Fall registration event.',
      },
      ticket: {id: 'ticket-fall', name: 'Fall General Admission'},
    }),
  });
  await mockEmailAuthFlow(page, {verifyResponse: loginResponse({user: {email}, next_step: 'account'})});
  await mockProfileEndpoint(page, {current: profileResponse({email})});

  await page.goto('/event-registration', {waitUntil: 'domcontentloaded'});
  await expect(page.getByRole('heading', {name: 'Spring Showcase'})).toBeVisible();
  await page.getByRole('button', {name: 'Register'}).nth(1).click();

  await expect(page.getByRole('heading', {name: 'Fall Showcase'})).toBeVisible();
  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', {name: 'Continue', exact: true}).click();
  await page.getByLabel('Verification Code').fill('123456');
  await page.getByRole('button', {name: 'Verify Code'}).click();

  await page.locator('#first-name').fill('Ada');
  await page.locator('#last-name').fill('Lovelace');
  await page.locator('#attendee-organization').fill('Acme Corp');
  await page.getByRole('radio', {name: 'Fall General Admission'}).click();
  await page.getByRole('button', {name: 'Register'}).click();

  await expect(page.getByRole('heading', {name: "You're Registered!"})).toBeVisible();
  expect(created[0]).toMatchObject({event_slug: 'fall-showcase', ticket_id: 'ticket-fall'});
});

test('account dashboard shows an existing registration and another open event', async ({page}) => {
  const existing = registration();
  await seedAuthenticatedSession(page, {mockDashboardSideEffects: false, user: {email: 'dashboard-events@example.com'}});
  await page.route('**/event/my-tickets/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify([existing])}),
  );
  await page.route('**/event/registration-events/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        registrationEvent({id: existing.event.id, name: existing.event.name, slug: existing.event.slug, registration: existing}),
        registrationEvent({id: 'event-fall', name: 'Fall Showcase', slug: 'fall-showcase', date: '2026-10-01'}),
      ]),
    }),
  );
  await page.route('**/authn/account-emails/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({emails: ['dashboard-events@example.com']})}),
  );
  await page.route('**/authn/contact-emails/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
  await page.route('**/authn/contact-phones/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );

  await page.goto('/account', {waitUntil: 'domcontentloaded'});

  await expect(page.getByText('E2E Showcase')).toBeVisible();
  await expect(page.getByText('Fall Showcase')).toBeVisible();
  await expect(page.getByRole('link', {name: 'Register for this event'})).toHaveAttribute(
    'href',
    '/event-registration?event=fall-showcase',
  );
});

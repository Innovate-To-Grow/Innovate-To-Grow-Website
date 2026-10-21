// Composable `page.route` installers. Each stubs one flow's endpoints and
// returns the captured request payloads for assertions. RegExp matchers are
// used where a request may carry a query string (glob `?`/`*` handling is
// finicky); exact slash-terminated paths use string globs.
import type {Page} from '@playwright/test';
import type {
  EventRegistrationOptions,
  EventRegistrationSummary,
  EventSchedulePayload,
  Registration,
} from '../../../src/features/events/api';
import {
  registration as buildRegistration,
  registrationEvent,
  registrationOptions,
} from '../factories';
import {mockSendVerification} from './authFlows';
import {json} from './json';

export interface EventRegistrationMockResult {
  created: unknown[];
  phoneCodeRequests: unknown[];
  phoneVerifications: unknown[];
  secondaryEmailCodeRequests: unknown[];
  secondaryEmailVerifications: unknown[];
}

export async function mockEventRegistration(
  page: Page,
  opts: {events?: EventRegistrationSummary[]; options?: EventRegistrationOptions; registration?: Registration} = {},
): Promise<EventRegistrationMockResult> {
  const created: unknown[] = [];
  const phoneCodeRequests: unknown[] = [];
  const phoneVerifications: unknown[] = [];
  const secondaryEmailCodeRequests: unknown[] = [];
  const secondaryEmailVerifications: unknown[] = [];
  const options = opts.options ?? registrationOptions();

  await mockSendVerification(page);

  await page.route('**/event/registration-options/**', (route) =>
    route.fulfill(json(options)),
  );
  await page.route('**/event/registration-events/', (route) =>
    route.fulfill(json(opts.events ?? [registrationEvent({
      id: options.id,
      name: options.name,
      slug: options.slug,
      date: options.date,
      location: options.location,
      description: options.description,
      registration: options.registration,
    })])),
  );

  await page.route('**/event/registrations/', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    created.push(route.request().postDataJSON());
    await route.fulfill(json(opts.registration ?? buildRegistration(), 201));
  });

  await page.route('**/event/send-phone-code/', (route) => {
    const payload = route.request().postDataJSON();
    phoneCodeRequests.push(payload);
    return route.fulfill(json({detail: 'Code sent.', phone: `+1${payload.phone}`, challenge_id: 'phone-challenge-e2e'}));
  });
  await page.route('**/event/verify-phone-code/', (route) => {
    const payload = route.request().postDataJSON();
    phoneVerifications.push(payload);
    return route.fulfill(json({detail: 'Verified.', verified: true, phone: payload.phone, challenge_id: 'phone-challenge-e2e'}));
  });
  await page.route('**/event/send-secondary-email-code/', (route) => {
    const payload = route.request().postDataJSON();
    secondaryEmailCodeRequests.push(payload);
    return route.fulfill(json({email: payload.email, challenge_id: 'email-challenge-e2e'}));
  });
  await page.route('**/event/verify-secondary-email-code/', (route) => {
    const payload = route.request().postDataJSON();
    secondaryEmailVerifications.push(payload);
    return route.fulfill(json({email: payload.email, verified: true, challenge_id: 'email-challenge-e2e', verification_token: 'email-proof-e2e'}));
  });
  await page.route('**/event/my-tickets/*/resend-email/', (route) =>
    route.fulfill(json({message: 'Email sent successfully.'})),
  );

  return {created, phoneCodeRequests, phoneVerifications, secondaryEmailCodeRequests, secondaryEmailVerifications};
}

export async function mockSchedule(page: Page, payload: EventSchedulePayload): Promise<void> {
  await page.route(/\/event\/schedule\//, (route) => route.fulfill(json(payload)));
}


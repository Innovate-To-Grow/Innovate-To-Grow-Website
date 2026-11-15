import {mintFakeJwt, mockAuthoritativeSession, mockProfileEndpoint, profileResponse} from '../../helpers';

export const PHONE = '2025550123';
export const PHONE_E164 = '+12025550123';

export function json(body: unknown, status = 200) {
  return {status, contentType: 'application/json', body: JSON.stringify(body)};
}

export async function stubAccountSideEffects(page: import('@playwright/test').Page) {
  // Phone-only account: no primary email yet.
  const profile = profileResponse({
    email: '',
    member_uuid: 'm-phone',
    primary_email_id: null,
    email_verified: false,
  });
  await mockProfileEndpoint(page, {current: profile});
  await mockAuthoritativeSession(
    page,
    {member_uuid: 'm-phone', email: '', phone: PHONE_E164},
    profile,
    false,
  );
  // Keep the just-logged-in session alive on /account. The mocked login mints a
  // fake access token, so any un-mocked authenticated side request can 401 against the real CI backend and
  // trips the api-client refresh->logout cascade, bouncing the user to /login
  // before the SMS code message can render. Make refresh succeed to defeat it.
  await page.route('**/authn/refresh/', (route) =>
    route.fulfill(json({access: mintFakeJwt(), refresh: 'refresh-e2e'})),
  );
  await page.route('**/event/my-tickets/', (route) => route.fulfill(json([])));
  await page.route('**/event/registration-events/', (route) => route.fulfill(json([])));
  await page.route('**/event/registration-options/**', (route) => route.fulfill(json({detail: 'none'}, 404)));
  await page.route('**/authn/account-emails/', (route) => route.fulfill(json({emails: []})));
  await page.route('**/authn/contact-emails/', (route) => route.fulfill(json([])));
  await page.route('**/projects/past-shares/mine/', (route) => route.fulfill(json([])));
  await page.route('**/authn/contact-phones/', (route) =>
    route.fulfill(json([{id: 'p-1', phone_number: PHONE, region: '1-US', region_display: 'United States', subscribe: false, verified: true, created_at: '2026-01-01T00:00:00Z'}])),
  );
}

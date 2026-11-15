import {type Page} from '@playwright/test';
import type {ProfileResponse, User} from '../../src/features/auth/api/contracts/types';
import {mintFakeJwt, profileResponse} from './factories';
import {
  AUTH_SESSION_KEY,
  mockAuthoritativeSession,
  mockSuccessfulRefresh,
  type SeedAuthOptions,
  type SeededSession,
  updateAuthoritativeProfile,
} from './session';

/**
 * Seed an authenticated session into storage BEFORE navigation via
 * `addInitScript`, so all three React roots render logged-in on first paint
 * (AuthContext reads storage synchronously on mount). Pairs with a profile
 * mock and the dashboard side-effect stubs. Must be called before page.goto.
 */
export async function seedAuthenticatedSession(
  page: Page,
  opts: SeedAuthOptions = {},
): Promise<SeededSession> {
  const user: User = {member_uuid: 'member-e2e', email: 'member@example.com', ...opts.user};
  const authEmails = user.email.includes('@') ? [user.email] : [];
  const access = mintFakeJwt({exp: opts.accessExp});

  await page.addInitScript(
    ({accessToken, refreshToken, userJson, completion, sessionKey}) => {
      localStorage.setItem(
        sessionKey,
        JSON.stringify({
          version: 1,
          generation: 'e2e-seeded-generation',
          access: accessToken,
          refresh: refreshToken,
          user: JSON.parse(userJson),
          requires_profile_completion: completion,
        }),
      );
    },
    {
      accessToken: access,
      refreshToken: 'refresh-e2e',
      userJson: JSON.stringify(user),
      completion: Boolean(opts.requiresProfileCompletion),
      sessionKey: AUTH_SESSION_KEY,
    },
  );

  // Any stray authenticated call that 401s against a live backend would trip
  // the api-client refresh→logout cascade (client.ts) and unmount guarded
  // pages mid-test. Make refresh succeed so a seeded session is never logged
  // out by an un-mocked request.
  await mockSuccessfulRefresh(page);

  const profileRef = {
    current: profileResponse({email: user.email, member_uuid: user.member_uuid, ...opts.profile}),
  };
  await mockAuthoritativeSession(
    page,
    user,
    profileRef.current,
    Boolean(opts.requiresProfileCompletion),
  );
  let patchPayloads: unknown[] = [];
  if (opts.mockProfile !== false) {
    patchPayloads = await mockProfileEndpoint(page, profileRef);
  }
  if (opts.mockDashboardSideEffects !== false) {
    await page.route('**/event/my-tickets/', (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
    );
    await page.route('**/event/registration-events/', (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
    );
    await page.route('**/event/registration-options/**', (route) =>
      route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({detail: 'No active event.'}),
      }),
    );
    // EmailCenter / PhoneCenter fetch these on mount; left unmocked against a
    // live backend they 401 with the fake token and trigger the logout cascade.
    await page.route('**/authn/account-emails/', (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({emails: authEmails})}),
    );
    await page.route('**/authn/contact-emails/', (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
    );
    await page.route('**/authn/contact-phones/', (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
    );
    await page.route('**/projects/past-shares/mine/', (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
    );
  }

  return {user, profileRef, patchPayloads};
}

/**
 * Stateful GET/PATCH `/authn/profile/` mock. GET returns the current profile;
 * PATCH merges the JSON body, records it, and returns the merged profile.
 */
export async function mockProfileEndpoint(
  page: Page,
  profileRef: {current: ProfileResponse},
): Promise<unknown[]> {
  const patchPayloads: unknown[] = [];
  await page.route('**/authn/profile/', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(profileRef.current),
      });
      return;
    }
    if (request.method() === 'PATCH') {
      let payload: Record<string, unknown>;
      try {
        payload = request.postDataJSON() as Record<string, unknown>;
      } catch {
        // Multipart (profile image) — keep raw text for assertions.
        payload = {raw: request.postData() ?? ''};
      }
      patchPayloads.push(payload);
      profileRef.current = {...profileRef.current, ...(payload as Partial<ProfileResponse>)};
      updateAuthoritativeProfile(page, profileRef.current);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(profileRef.current),
      });
      return;
    }
    await route.fulfill({status: 405});
  });
  return patchPayloads;
}

/**
 * Stub the endpoints AccountPage fires on mount so navigating to /account does
 * not hang on un-mocked network. Covers the dashboard data calls (`getProfile`,
 * `fetchMyTickets`, `fetchRegistrationEvents`) AND the EmailCenter/PhoneCenter
 * mounts (`account-emails`, `contact-emails`, `contact-phones`) plus a
 * succeeding `refresh`. The session-guard mocks are load-bearing: left unmocked
 * they 401 against the live E2E backend with the fake token, and the api-client
 * refresh->logout cascade (client.ts) tears down the just-established session —
 * racing the menu-flip assertion and, on slower engines (webkit) reached via the
 * extra /magic-login,/ticket-login redirect hop, beating it. Mirrors the guard
 * mocks in seedAuthenticatedSession. Use when a flow lands on /account but the
 * test isn't asserting dashboard internals.
 */
export async function mockAccountDashboard(
  page: Page,
  opts: {email?: string} = {},
): Promise<void> {
  const email = opts.email ?? 'member@example.com';
  const authEmails = email.includes('@') ? [email] : [];
  const profileRef = {current: profileResponse({email})};
  await mockProfileEndpoint(page, profileRef);
  await mockAuthoritativeSession(
    page,
    {member_uuid: profileRef.current.member_uuid, email},
    profileRef.current,
    false,
  );
  await page.route('**/event/my-tickets/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
  await page.route('**/event/registration-events/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
  await page.route('**/event/registration-options/**', (route) =>
    route.fulfill({status: 404, contentType: 'application/json', body: JSON.stringify({detail: 'none'})}),
  );
  // Keep a seeded session alive on /account: an un-mocked 401 here would trip
  // the refresh->logout cascade and sign the member back out.
  await mockSuccessfulRefresh(page);
  await page.route('**/authn/account-emails/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({emails: authEmails})}),
  );
  await page.route('**/authn/contact-emails/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
  await page.route('**/authn/contact-phones/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
  await page.route('**/projects/past-shares/mine/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
}

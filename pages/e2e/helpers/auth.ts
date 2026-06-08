import {expect, type Page} from '@playwright/test';
import type {ProfileResponse, User} from '../../src/features/auth/api/types';
import {mintFakeJwt, profileResponse} from './factories';

// Storage keys mirror pages/src/features/auth/api/storage.ts. Kept as literals
// here because addInitScript serializes its callback into the browser context
// and cannot import app modules.
const ACCESS_TOKEN_KEY = 'i2g_access_token';
const REFRESH_TOKEN_KEY = 'i2g_refresh_token';
const USER_KEY = 'i2g_user';
const PROFILE_COMPLETION_REQUIRED_KEY = 'i2g_profile_completion_required';

export interface SeedAuthOptions {
  user?: Partial<User>;
  accessExp?: number;
  requiresProfileCompletion?: boolean;
  profile?: Partial<ProfileResponse>;
  /** Install the GET/PATCH /authn/profile/ mock (default true). */
  mockProfile?: boolean;
  /**
   * Stub the AccountPage mount calls that fire unconditionally so they don't
   * hit the live origin and hang the page (default true).
   */
  mockDashboardSideEffects?: boolean;
}

export interface SeededSession {
  user: User;
  profileRef: {current: ProfileResponse};
  patchPayloads: unknown[];
}

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
  const access = mintFakeJwt({exp: opts.accessExp});

  await page.addInitScript(
    ({accessToken, refreshToken, userJson, completion, keys}) => {
      localStorage.setItem(keys.access, accessToken);
      localStorage.setItem(keys.refresh, refreshToken);
      localStorage.setItem(keys.user, userJson);
      if (completion) {
        sessionStorage.setItem(keys.completion, 'true');
      }
    },
    {
      accessToken: access,
      refreshToken: 'refresh-e2e',
      userJson: JSON.stringify(user),
      completion: Boolean(opts.requiresProfileCompletion),
      keys: {
        access: ACCESS_TOKEN_KEY,
        refresh: REFRESH_TOKEN_KEY,
        user: USER_KEY,
        completion: PROFILE_COMPLETION_REQUIRED_KEY,
      },
    },
  );

  // Any stray authenticated call that 401s against a live backend would trip
  // the api-client refresh→logout cascade (client.ts) and unmount guarded
  // pages mid-test. Make refresh succeed so a seeded session is never logged
  // out by an un-mocked request.
  await page.route('**/authn/refresh/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({access: mintFakeJwt(), refresh: 'refresh-e2e'}),
    }),
  );

  const profileRef = {
    current: profileResponse({email: user.email, member_uuid: user.member_uuid, ...opts.profile}),
  };
  let patchPayloads: unknown[] = [];
  if (opts.mockProfile !== false) {
    patchPayloads = await mockProfileEndpoint(page, profileRef);
  }
  if (opts.mockDashboardSideEffects !== false) {
    await page.route('**/event/my-tickets/', (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
    );
    await page.route('**/event/registration-options/', (route) =>
      route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({detail: 'No active event.'}),
      }),
    );
    // EmailCenter / PhoneCenter fetch these on mount; left unmocked against a
    // live backend they 401 with the fake token and trigger the logout cascade.
    await page.route('**/authn/account-emails/', (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({emails: [user.email]})}),
    );
    await page.route('**/authn/contact-emails/', (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
    );
    await page.route('**/authn/contact-phones/', (route) =>
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
      let payload: Record<string, unknown> = {};
      try {
        payload = request.postDataJSON() as Record<string, unknown>;
      } catch {
        // Multipart (profile image) — keep raw text for assertions.
        payload = {raw: request.postData() ?? ''};
      }
      patchPayloads.push(payload);
      profileRef.current = {...profileRef.current, ...(payload as Partial<ProfileResponse>)};
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
 * `fetchMyTickets`, `fetchRegistrationOptions`) AND the EmailCenter/PhoneCenter
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
  await mockProfileEndpoint(page, {current: profileResponse({email})});
  await page.route('**/event/my-tickets/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
  await page.route('**/event/registration-options/', (route) =>
    route.fulfill({status: 404, contentType: 'application/json', body: JSON.stringify({detail: 'none'})}),
  );
  // Keep a seeded session alive on /account: an un-mocked 401 here would trip
  // the refresh->logout cascade and sign the member back out.
  await page.route('**/authn/refresh/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({access: mintFakeJwt(), refresh: 'refresh-e2e'}),
    }),
  );
  await page.route('**/authn/account-emails/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({emails: [email]})}),
  );
  await page.route('**/authn/contact-emails/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
  await page.route('**/authn/contact-phones/', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: '[]'}),
  );
}

// A real RSA-2048 SPKI public key so the browser's Web Crypto
// `importKey('spki', …, {name:'RSA-OAEP', hash:'SHA-256'})` succeeds for the
// password-confirm flows. Encryption output is never decrypted by the mocks —
// specs assert the request body SHAPE, not the plaintext.
export const MOCK_RSA_PUBLIC_KEY_PEM = `-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuZH0ooTxP1mSaA+q1cmX
t22LrYF+n5SrQ7uk9mZWKJYrsAFZbC9gAkqRc1+wXa0zRUoaNe26czJyx0BfXSLc
VhTo5uGfIcz3t8gVUz6jG91QCjaBNKzvarbCfvYIXlXlZZEyG8SpCIHxEwTbW46A
cKUHmrW54Chp6eOFkPoZG8hTllI214eitYBqRvp+1WMAJao29zP5GOFwon31rj6s
ALlPDE79H+9x8+QRI+mexhMqg4nGA9iLcMFrJA3y6+Ac+n8hUnIvlp+j1AfAWeKf
A5K7SCSlT4nt8j5SSgwXg0N4xMu/EpWf0UsjpC6KTDo679ANMQTcZUNzwOGz/Wds
FQIDAQAB
-----END PUBLIC KEY-----`;

/** Serve the encryption public key so RSA-OAEP password flows can run. */
export async function mockPublicKey(page: Page): Promise<void> {
  await page.route('**/authn/public-key/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({public_key: MOCK_RSA_PUBLIC_KEY_PEM, key_id: 'e2e-key'}),
    }),
  );
}

// Cross-root observable: #menu-root reflects auth state in BOTH the desktop
// MemberMenu (.member-name / "Sign In") and the off-canvas MobileMenuPanel
// (.header-mobile-member). Both are always in the DOM (one hidden per
// viewport), so we assert on the menu root's text content — viewport-agnostic
// and immune to the off-canvas element still matching role/visibility queries.
// "Sign In" appears only when signed out (signed-in shows "Sign Out"/"Account"
// + the member email); the member email appears only when signed in.
export async function expectSignedOut(page: Page): Promise<void> {
  await expect(page.locator('#menu-root')).toContainText('Sign In');
}

export async function expectSignedInAs(page: Page, email: string): Promise<void> {
  await expect(page.locator('#menu-root')).toContainText(email);
}

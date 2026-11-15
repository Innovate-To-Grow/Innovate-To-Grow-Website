import {expect, type Page} from '@playwright/test';
import type {LoginResponse, ProfileResponse, User} from '../../src/features/auth/api/contracts/types';
import {mintFakeJwt, profileResponse} from './factories';

// Storage keys mirror pages/src/features/auth/api/session/storage.ts. Kept as literals
// here because addInitScript serializes its callback into the browser context
// and cannot import app modules.
export const AUTH_SESSION_KEY = 'i2g_auth_session';

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

interface AuthoritativeSessionState {
  user: User;
  profile: ProfileResponse;
  requiresProfileCompletion: boolean;
}

const authoritativeSessions = new WeakMap<Page, AuthoritativeSessionState>();
const sessionRoutes = new WeakSet<Page>();
const refreshRoutes = new WeakSet<Page>();

export async function mockSuccessfulRefresh(page: Page): Promise<void> {
  if (refreshRoutes.has(page)) return;

  refreshRoutes.add(page);
  await page.route('**/authn/refresh/', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({access: mintFakeJwt(), refresh: 'refresh-e2e'}),
    }),
  );
}

export async function mockAuthoritativeSession(
  page: Page,
  user: User,
  profile: ProfileResponse,
  requiresProfileCompletion: boolean,
): Promise<void> {
  authoritativeSessions.set(page, {user, profile, requiresProfileCompletion});
  if (sessionRoutes.has(page)) return;

  sessionRoutes.add(page);
  await page.route('**/authn/session/', (route) => {
    const session = authoritativeSessions.get(page);
    if (!session) {
      return route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({detail: 'Authentication credentials were not provided.'}),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user: {
          ...session.profile,
          phone: session.user.phone ?? '',
          is_staff: Boolean(session.user.is_staff),
        },
        requires_profile_completion: session.requiresProfileCompletion,
        next_step: session.requiresProfileCompletion ? 'complete_profile' : 'account',
      }),
    });
  });
}

/**
 * Keep the authoritative session endpoint aligned with a successful mocked
 * login response. Call this again when the login request resolves so a setup
 * helper installed later cannot replace the newly authenticated identity.
 */
export async function mockAuthenticatedLogin(page: Page, response: LoginResponse): Promise<void> {
  const profile = profileResponse({
    member_uuid: response.user.member_uuid,
    email: response.user.email,
    is_staff: Boolean(response.user.is_staff),
    profile_image: response.user.profile_image,
  });
  await mockAuthoritativeSession(
    page,
    response.user,
    profile,
    Boolean(response.requires_profile_completion),
  );
  await mockSuccessfulRefresh(page);
}

export function updateAuthoritativeProfile(page: Page, profile: ProfileResponse): void {
  const session = authoritativeSessions.get(page);
  if (!session) return;
  session.profile = profile;
  if (
    profile.first_name.trim() &&
    profile.last_name.trim() &&
    profile.organization.trim()
  ) {
    session.requiresProfileCompletion = false;
  }
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

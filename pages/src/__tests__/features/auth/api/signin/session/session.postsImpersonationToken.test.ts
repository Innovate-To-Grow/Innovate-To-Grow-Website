import {beforeEach, describe, expect, it, vi} from 'vitest';
import {baseSession} from '@/__tests__/features/auth/api/signin/session/sessionFixtures';

const authApiPost = vi.fn();
const authApiGet = vi.fn();
const clearTokens = vi.fn();
const persistAuthSession = vi.fn();
const updateStoredSessionProfile = vi.fn();
const isDefinitiveAuthFailure = vi.fn((error: unknown) =>
  Boolean(
    error &&
      typeof error === 'object' &&
      (error as {definitive?: boolean}).definitive,
  ),
);

let storedSession: typeof baseSession | null;

vi.mock('@/features/auth/api/session/client', () => ({
  authApi: {get: authApiGet, post: authApiPost},
  isDefinitiveAuthFailure,
}));

vi.mock('@/features/auth/api/session/storage', () => ({
  clearTokens,
  getAccessToken: vi.fn(() => storedSession?.access ?? null),
  getStoredSession: vi.fn(() => storedSession),
  persistAuthSession,
  updateStoredSessionProfile,
}));

describe('auth session lifecycle', () => {
  beforeEach(() => {
    vi.resetModules();
    authApiGet.mockReset();
    authApiPost.mockReset();
    clearTokens.mockReset();
    persistAuthSession.mockReset();
    updateStoredSessionProfile.mockReset();
    storedSession = {...baseSession, user: {...baseSession.user}};
    clearTokens.mockImplementation(() => {
      storedSession = null;
      return true;
    });
    updateStoredSessionProfile.mockImplementation(
      (
        _guard: unknown,
        user: typeof baseSession.user,
        requiresProfileCompletion: boolean,
      ) => {
        if (!storedSession) return null;
        storedSession = {
          ...storedSession,
          user,
          requires_profile_completion: requiresProfileCompletion,
        };
        return storedSession;
      },
    );
  });

  const loginData = () => ({
    access: 'a',
    refresh: 'r',
    user: {member_uuid: 'member-b', email: 'new@example.com'},
  });

  // Not a login response: what a proxy, captive portal, or SPA rewrite answers
  // with on a 2xx.
  const MALFORMED_BODIES: Array<[string, unknown]> = [
    ['an HTML page', '<!doctype html><html></html>'],
    ['an empty body', ''],
    ['null', null],
    ['an array', []],
    ['an object without tokens', {message: 'ok', user: {member_uuid: 'm', email: 'e@example.com'}}],
    ['an empty access token', {...loginData(), access: ''}],
    ['a non-string refresh token', {...loginData(), refresh: 7}],
    ['no user', {access: 'a', refresh: 'r'}],
    ['a null user', {access: 'a', refresh: 'r', user: null}],
    ['a string user', {access: 'a', refresh: 'r', user: 'ada'}],
    ['a user without member_uuid', {access: 'a', refresh: 'r', user: {email: 'e@example.com'}}],
    ['a user without an email', {access: 'a', refresh: 'r', user: {member_uuid: 'm'}}],
  ];

  it('posts an impersonation token and persists the returned session', async () => {
    const data = loginData();
    authApiPost.mockResolvedValue({data});
    const {impersonateAutoLogin} = await import('@/features/auth/api/signin/session');

    const result = await impersonateAutoLogin('token-3');

    expect(authApiPost).toHaveBeenCalledWith(
      '/authn/impersonate-login/',
      {token: 'token-3'},
      {skipAuth: true},
    );
    expect(persistAuthSession).toHaveBeenCalledWith(data);
    expect(result).toBe(data);
  });

  it.each(MALFORMED_BODIES)(
    'rejects an impersonation 2xx answer that is %s without touching storage',
    async (_label, data) => {
      authApiPost.mockResolvedValue({data});
      const {impersonateAutoLogin} = await import('@/features/auth/api/signin/session');
      const {MalformedLoginResponseError} = await import('@/features/auth/api/contracts/errors');

      await expect(impersonateAutoLogin('token-x')).rejects.toBeInstanceOf(
        MalformedLoginResponseError,
      );
      expect(persistAuthSession).not.toHaveBeenCalled();
    },
  );

  it('reports unauthenticated when no access token is stored', async () => {
    storedSession = null;
    const {isAuthenticated} = await import('@/features/auth/api/signin/session');
    expect(isAuthenticated()).toBe(false);
  });

  it('accepts an unexpired JWT access token', async () => {
    const token = `header.${btoa(JSON.stringify({exp: 2000000000}))}.signature`;
    storedSession = {...baseSession, access: token};
    const {isAuthenticated} = await import('@/features/auth/api/signin/session');
    expect(isAuthenticated()).toBe(true);
  });

  it('rejects an expired JWT access token', async () => {
    const token = `header.${btoa(JSON.stringify({exp: 1}))}.signature`;
    storedSession = {...baseSession, access: token};
    const {isAuthenticated} = await import('@/features/auth/api/signin/session');
    expect(isAuthenticated()).toBe(false);
  });

  it('rejects a token whose payload exp is not numeric', async () => {
    const token = `header.${btoa(JSON.stringify({exp: 'soon'}))}.signature`;
    storedSession = {...baseSession, access: token};
    const {isAuthenticated} = await import('@/features/auth/api/signin/session');
    expect(isAuthenticated()).toBe(false);
  });

  it('rejects a token without a payload segment', async () => {
    storedSession = {...baseSession, access: 'no-dot-token'};
    const {isAuthenticated} = await import('@/features/auth/api/signin/session');
    expect(isAuthenticated()).toBe(false);
  });

  it('rejects a token with an undecodable payload', async () => {
    storedSession = {...baseSession, access: 'a.!!!.b'};
    const {isAuthenticated} = await import('@/features/auth/api/signin/session');
    expect(isAuthenticated()).toBe(false);
  });

  it('resolves anonymous without a request when no session is stored', async () => {
    storedSession = null;
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    await expect(bootstrapAuthSession()).resolves.toEqual({status: 'anonymous', session: null});
    expect(authApiGet).not.toHaveBeenCalled();
  });

  it('clears and dispatches when the endpoint reports authenticated=false', async () => {
    authApiGet.mockResolvedValue({data: {authenticated: false}});
    const eventSpy = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventSpy);
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    await expect(bootstrapAuthSession()).resolves.toEqual({status: 'anonymous', session: null});

    expect(clearTokens).toHaveBeenCalledWith({generation: 'generation-a', refresh: 'refresh-token'});
    expect(eventSpy).toHaveBeenCalledTimes(1);
    window.removeEventListener('i2g-auth-state-change', eventSpy);
  });

  it('keeps the session verified when the payload has no usable member', async () => {
    authApiGet.mockResolvedValue({data: {user: {member_uuid: ''}}});
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    const result = await bootstrapAuthSession();

    expect(result).toMatchObject({status: 'verified', session: baseSession});
    expect(updateStoredSessionProfile).not.toHaveBeenCalled();
  });
});

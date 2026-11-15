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

  it('clears the guarded session when the authoritative endpoint rejects it', async () => {
    authApiGet.mockRejectedValue({
      response: {status: 401},
      definitive: true,
    });
    const eventSpy = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventSpy);
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    await expect(bootstrapAuthSession()).resolves.toEqual({
      status: 'anonymous',
      session: null,
    });

    expect(clearTokens).toHaveBeenCalledWith({
      generation: 'generation-a',
      refresh: 'refresh-token',
    });
    expect(eventSpy).toHaveBeenCalledTimes(1);
    window.removeEventListener('i2g-auth-state-change', eventSpy);
  });

  it('preserves an expired session when refresh failed transiently', async () => {
    const transientRefreshFailure = {response: {status: 401}};
    authApiGet.mockRejectedValue(transientRefreshFailure);
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    await expect(bootstrapAuthSession()).resolves.toEqual({
      status: 'unverified',
      session: baseSession,
    });

    expect(isDefinitiveAuthFailure).toHaveBeenCalledWith(
      transientRefreshFailure,
    );
    expect(clearTokens).not.toHaveBeenCalled();
    expect(storedSession).toEqual(baseSession);
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

  it('posts a login-link token and persists the returned session', async () => {
    const data = loginData();
    authApiPost.mockResolvedValue({data});
    const {loginLinkAutoLogin} = await import('@/features/auth/api/signin/session');

    const result = await loginLinkAutoLogin('token-1');

    expect(authApiPost).toHaveBeenCalledWith(
      '/mail/login-link/',
      {token: 'token-1'},
      {skipAuth: true},
    );
    expect(persistAuthSession).toHaveBeenCalledWith(data);
    expect(result).toBe(data);
  });

  it('accepts a phone-only account, whose email is an empty string', async () => {
    const data = {...loginData(), user: {member_uuid: 'member-p', email: ''}};
    authApiPost.mockResolvedValue({data});
    const {loginLinkAutoLogin} = await import('@/features/auth/api/signin/session');

    await expect(loginLinkAutoLogin('token-p')).resolves.toBe(data);
    expect(persistAuthSession).toHaveBeenCalledWith(data);
  });

  it.each(MALFORMED_BODIES)(
    'rejects a login-link 2xx answer that is %s without touching storage',
    async (_label, data) => {
      authApiPost.mockResolvedValue({data});
      const {loginLinkAutoLogin} = await import('@/features/auth/api/signin/session');
      const {MalformedLoginResponseError} = await import('@/features/auth/api/contracts/errors');

      await expect(loginLinkAutoLogin('token-x')).rejects.toBeInstanceOf(
        MalformedLoginResponseError,
      );
      expect(persistAuthSession).not.toHaveBeenCalled();
    },
  );

  it('lets the typed storage failure through untouched when the session cannot be written', async () => {
    authApiPost.mockResolvedValue({data: loginData()});
    const {loginLinkAutoLogin} = await import('@/features/auth/api/signin/session');
    const {SessionNotSavedError} = await import('@/features/auth/api/contracts/errors');
    const failure = new SessionNotSavedError();
    persistAuthSession.mockImplementation(() => {
      throw failure;
    });

    await expect(loginLinkAutoLogin('token-y')).rejects.toBe(failure);
  });

  it('passes an Axios failure through untouched', async () => {
    const failure = Object.assign(new Error('Request failed'), {isAxiosError: true});
    authApiPost.mockRejectedValue(failure);
    const {loginLinkAutoLogin} = await import('@/features/auth/api/signin/session');

    await expect(loginLinkAutoLogin('token-z')).rejects.toBe(failure);
    expect(persistAuthSession).not.toHaveBeenCalled();
  });
});

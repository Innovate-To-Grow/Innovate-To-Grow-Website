import {beforeEach, describe, expect, it, vi} from 'vitest';

const authApiPost = vi.fn();
const clearTokens = vi.fn();
const getAccessToken = vi.fn<() => string | null>(() => 'access-token');
const getRefreshToken = vi.fn<() => string | null>(() => 'refresh-token');
const persistAuthSession = vi.fn();

vi.mock('@/features/auth/api/client', () => ({
  authApi: {post: authApiPost},
}));

vi.mock('@/features/auth/api/storage', () => ({
  clearTokens,
  clearProfileCompletionRequired: vi.fn(),
  getAccessToken,
  getRefreshToken,
  persistAuthSession,
  setTokens: vi.fn(),
}));

const makeToken = (payload: Record<string, unknown>) => `header.${btoa(JSON.stringify(payload))}.signature`;

describe('auth session API', () => {
  beforeEach(() => {
    vi.resetModules();
    authApiPost.mockReset();
    clearTokens.mockReset();
    getAccessToken.mockReset();
    getRefreshToken.mockReset();
    persistAuthSession.mockReset();
    getAccessToken.mockReturnValue('access-token');
    getRefreshToken.mockReturnValue('refresh-token');
  });

  it('clears tokens and dispatches the auth-state event even when the server call is still in flight', async () => {
    // The server POST never resolves — if logout() waited on it, clearTokens
    // would never fire and the user would remain effectively logged in.
    authApiPost.mockReturnValue(new Promise(() => undefined));
    const eventSpy = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventSpy);

    const {logout} = await import('@/features/auth/api/session');

    // Not awaited — proves local work doesn't depend on the server call.
    void logout();

    // Microtask drain: the synchronous path up to the server POST must have
    // run, which means clearTokens + event dispatch already happened.
    await Promise.resolve();

    expect(clearTokens).toHaveBeenCalledTimes(1);
    expect(eventSpy).toHaveBeenCalledTimes(1);
    expect(authApiPost).toHaveBeenCalledWith('/authn/logout/', {refresh: 'refresh-token'});

    window.removeEventListener('i2g-auth-state-change', eventSpy);
  });

  it('clears tokens before the server POST is dispatched, so listeners read empty storage', async () => {
    const callOrder: string[] = [];
    clearTokens.mockImplementation(() => callOrder.push('clearTokens'));
    authApiPost.mockImplementation(() => {
      callOrder.push('authApi.post');
      return Promise.resolve({data: {}});
    });

    const {logout} = await import('@/features/auth/api/session');
    await logout();

    expect(callOrder).toEqual(['clearTokens', 'authApi.post']);
  });

  it('does not call the server when there is no refresh token', async () => {
    getRefreshToken.mockReturnValue(null);
    const {logout} = await import('@/features/auth/api/session');

    await logout();

    expect(clearTokens).toHaveBeenCalledTimes(1);
    expect(authApiPost).not.toHaveBeenCalled();
  });

  it('swallows server errors without leaving local state in a half-cleared shape', async () => {
    authApiPost.mockRejectedValue(new Error('network down'));
    const {logout} = await import('@/features/auth/api/session');

    // Must not reject — local logout has already completed.
    await expect(logout()).resolves.toBeUndefined();
    expect(clearTokens).toHaveBeenCalledTimes(1);
    // Let the rejected promise settle so vitest doesn't warn about an
    // unhandled rejection.
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  it('auto-logins through token endpoints and persists returned sessions when appropriate', async () => {
    const loginResponse = {access: 'access', refresh: 'refresh', user: {email: 'member@example.com'}};
    const unsubscribeResponse = {message: 'ok', unsubscribed: true};
    authApiPost
      .mockResolvedValueOnce({data: loginResponse})
      .mockResolvedValueOnce({data: unsubscribeResponse})
      .mockResolvedValueOnce({data: loginResponse});

    const {impersonateAutoLogin, loginLinkAutoLogin, unsubscribeAutoLogin} = await import('@/features/auth/api/session');

    await expect(loginLinkAutoLogin('login-token')).resolves.toEqual(loginResponse);
    await expect(unsubscribeAutoLogin('unsubscribe-token')).resolves.toEqual(unsubscribeResponse);
    await expect(impersonateAutoLogin('impersonate-token')).resolves.toEqual(loginResponse);

    expect(authApiPost).toHaveBeenNthCalledWith(1, '/mail/login-link/', {token: 'login-token'});
    expect(authApiPost).toHaveBeenNthCalledWith(2, '/authn/unsubscribe-login/', {token: 'unsubscribe-token'});
    expect(authApiPost).toHaveBeenNthCalledWith(3, '/authn/impersonate-login/', {token: 'impersonate-token'});
    expect(persistAuthSession).toHaveBeenCalledTimes(2);
  });

  it('checks JWT expiry before reporting authentication', async () => {
    const {isAuthenticated} = await import('@/features/auth/api/session');

    getAccessToken.mockReturnValue(makeToken({exp: Date.now() / 1000 + 60}));
    expect(isAuthenticated()).toBe(true);

    getAccessToken.mockReturnValue(makeToken({exp: Date.now() / 1000 - 60}));
    expect(isAuthenticated()).toBe(false);

    getAccessToken.mockReturnValue(makeToken({sub: 'member'}));
    expect(isAuthenticated()).toBe(false);

    getAccessToken.mockReturnValue('not-a-jwt');
    expect(isAuthenticated()).toBe(false);

    getAccessToken.mockReturnValue(null);
    expect(isAuthenticated()).toBe(false);
  });
});

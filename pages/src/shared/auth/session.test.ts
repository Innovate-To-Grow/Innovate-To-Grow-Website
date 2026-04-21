import {beforeEach, describe, expect, it, vi} from 'vitest';

const authApiPost = vi.fn();
const clearTokens = vi.fn();
const getRefreshToken = vi.fn<() => string | null>(() => 'refresh-token');
const persistAuthSession = vi.fn();

vi.mock('./client', () => ({
  default: {post: authApiPost},
}));

vi.mock('./storage', () => ({
  clearTokens,
  clearProfileCompletionRequired: vi.fn(),
  getAccessToken: vi.fn(() => 'access-token'),
  getRefreshToken,
  persistAuthSession,
  setTokens: vi.fn(),
}));

describe('logout clears local state before awaiting server', () => {
  beforeEach(() => {
    vi.resetModules();
    authApiPost.mockReset();
    clearTokens.mockReset();
    getRefreshToken.mockReset();
    persistAuthSession.mockReset();
    getRefreshToken.mockReturnValue('refresh-token');
  });

  it('clears tokens and dispatches the auth-state event even when the server call is still in flight', async () => {
    // The server POST never resolves — if logout() waited on it, clearTokens
    // would never fire and the user would remain effectively logged in.
    authApiPost.mockReturnValue(new Promise(() => undefined));
    const eventSpy = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventSpy);

    const {logout} = await import('./session');

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

    const {logout} = await import('./session');
    await logout();

    expect(callOrder).toEqual(['clearTokens', 'authApi.post']);
  });

  it('does not call the server when there is no refresh token', async () => {
    getRefreshToken.mockReturnValue(null);
    const {logout} = await import('./session');

    await logout();

    expect(clearTokens).toHaveBeenCalledTimes(1);
    expect(authApiPost).not.toHaveBeenCalled();
  });

  it('swallows server errors without leaving local state in a half-cleared shape', async () => {
    authApiPost.mockRejectedValue(new Error('network down'));
    const {logout} = await import('./session');

    // Must not reject — local logout has already completed.
    await expect(logout()).resolves.toBeUndefined();
    expect(clearTokens).toHaveBeenCalledTimes(1);
    // Let the rejected promise settle so vitest doesn't warn about an
    // unhandled rejection.
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
});

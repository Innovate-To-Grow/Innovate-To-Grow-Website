import {beforeEach, describe, expect, it, vi} from 'vitest';

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

const baseSession = {
  version: 1 as const,
  generation: 'generation-a',
  access: 'access-token',
  refresh: 'refresh-token',
  user: {
    member_uuid: 'member-a',
    email: 'old@example.com',
    is_staff: false,
  },
  requires_profile_completion: false,
};

let storedSession: typeof baseSession | null;

vi.mock('@/features/auth/api/client', () => ({
  authApi: {get: authApiGet, post: authApiPost},
  isDefinitiveAuthFailure,
}));

vi.mock('@/features/auth/api/storage', () => ({
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

  it('clears local state before an unresolved server logout', async () => {
    authApiPost.mockReturnValue(new Promise(() => undefined));
    const eventSpy = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventSpy);
    const {logout} = await import('@/features/auth/api/session');

    void logout();
    await Promise.resolve();

    expect(clearTokens).toHaveBeenCalledWith({
      generation: 'generation-a',
      refresh: 'refresh-token',
    });
    expect(eventSpy).toHaveBeenCalledTimes(1);
    expect(authApiPost).toHaveBeenCalledWith('/authn/logout/', {
      refresh: 'refresh-token',
    });
    window.removeEventListener('i2g-auth-state-change', eventSpy);
  });

  it('clears the guarded record before dispatching the server request', async () => {
    const callOrder: string[] = [];
    clearTokens.mockImplementation(() => {
      callOrder.push('clearTokens');
      storedSession = null;
      return true;
    });
    authApiPost.mockImplementation(() => {
      callOrder.push('authApi.post');
      return Promise.resolve({data: {}});
    });
    const {logout} = await import('@/features/auth/api/session');

    await logout();
    expect(callOrder).toEqual(['clearTokens', 'authApi.post']);
  });

  it('does not call the server when no session is stored', async () => {
    storedSession = null;
    const {logout} = await import('@/features/auth/api/session');

    await logout();
    expect(clearTokens).toHaveBeenCalledWith(undefined);
    expect(authApiPost).not.toHaveBeenCalled();
  });

  it('swallows server logout errors after local state is cleared', async () => {
    authApiPost.mockRejectedValue(new Error('network down'));
    const {logout} = await import('@/features/auth/api/session');

    await expect(logout()).resolves.toBeUndefined();
    expect(clearTokens).toHaveBeenCalledTimes(1);
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  it('hydrates authoritative user and completion state from /authn/session/', async () => {
    authApiGet.mockResolvedValue({
      data: {
        user: {
          member_uuid: 'member-a',
          email: 'current@example.com',
          phone: '+12025550123',
          profile_image: '/media/avatar.png',
          is_staff: true,
          first_name: '',
          last_name: 'Member',
          organization: 'UC Merced',
        },
        requires_profile_completion: true,
        next_step: 'complete_profile',
      },
    });
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    const result = await bootstrapAuthSession();

    expect(authApiGet).toHaveBeenCalledWith('/authn/session/');
    expect(updateStoredSessionProfile).toHaveBeenCalledWith(
      {generation: 'generation-a', refresh: 'refresh-token'},
      expect.objectContaining({
        member_uuid: 'member-a',
        email: 'current@example.com',
        phone: '+12025550123',
        profile_image: '/media/avatar.png',
        is_staff: true,
      }),
      true,
    );
    expect(result).toMatchObject({
      status: 'verified',
      session: {user: {email: 'current@example.com'}},
    });
  });

  it('clears the guarded session when the authoritative endpoint rejects it', async () => {
    authApiGet.mockRejectedValue({
      response: {status: 401},
      definitive: true,
    });
    const eventSpy = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventSpy);
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

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
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

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

  it('posts a login-link token and persists the returned session', async () => {
    const data = {access: 'a', refresh: 'r', user: {}};
    authApiPost.mockResolvedValue({data});
    const {loginLinkAutoLogin} = await import('@/features/auth/api/session');

    const result = await loginLinkAutoLogin('token-1');

    expect(authApiPost).toHaveBeenCalledWith('/mail/login-link/', {token: 'token-1'});
    expect(persistAuthSession).toHaveBeenCalledWith(data);
    expect(result).toBe(data);
  });

  it('exchanges an unsubscribe token without persisting a session', async () => {
    const data = {message: 'unsubscribed'};
    authApiPost.mockResolvedValue({data});
    const {unsubscribeAutoLogin} = await import('@/features/auth/api/session');

    const result = await unsubscribeAutoLogin('token-2');

    expect(authApiPost).toHaveBeenCalledWith('/authn/unsubscribe-login/', {token: 'token-2'});
    expect(persistAuthSession).not.toHaveBeenCalled();
    expect(result).toBe(data);
  });

  it('posts an impersonation token and persists the returned session', async () => {
    const data = {access: 'a', refresh: 'r', user: {}};
    authApiPost.mockResolvedValue({data});
    const {impersonateAutoLogin} = await import('@/features/auth/api/session');

    const result = await impersonateAutoLogin('token-3');

    expect(authApiPost).toHaveBeenCalledWith('/authn/impersonate-login/', {token: 'token-3'});
    expect(persistAuthSession).toHaveBeenCalledWith(data);
    expect(result).toBe(data);
  });

  it('reports unauthenticated when no access token is stored', async () => {
    storedSession = null;
    const {isAuthenticated} = await import('@/features/auth/api/session');
    expect(isAuthenticated()).toBe(false);
  });

  it('accepts an unexpired JWT access token', async () => {
    const token = `header.${btoa(JSON.stringify({exp: 2000000000}))}.signature`;
    storedSession = {...baseSession, access: token};
    const {isAuthenticated} = await import('@/features/auth/api/session');
    expect(isAuthenticated()).toBe(true);
  });

  it('rejects an expired JWT access token', async () => {
    const token = `header.${btoa(JSON.stringify({exp: 1}))}.signature`;
    storedSession = {...baseSession, access: token};
    const {isAuthenticated} = await import('@/features/auth/api/session');
    expect(isAuthenticated()).toBe(false);
  });

  it('rejects a token whose payload exp is not numeric', async () => {
    const token = `header.${btoa(JSON.stringify({exp: 'soon'}))}.signature`;
    storedSession = {...baseSession, access: token};
    const {isAuthenticated} = await import('@/features/auth/api/session');
    expect(isAuthenticated()).toBe(false);
  });

  it('rejects a token without a payload segment', async () => {
    storedSession = {...baseSession, access: 'no-dot-token'};
    const {isAuthenticated} = await import('@/features/auth/api/session');
    expect(isAuthenticated()).toBe(false);
  });

  it('rejects a token with an undecodable payload', async () => {
    storedSession = {...baseSession, access: 'a.!!!.b'};
    const {isAuthenticated} = await import('@/features/auth/api/session');
    expect(isAuthenticated()).toBe(false);
  });

  it('resolves anonymous without a request when no session is stored', async () => {
    storedSession = null;
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    await expect(bootstrapAuthSession()).resolves.toEqual({status: 'anonymous', session: null});
    expect(authApiGet).not.toHaveBeenCalled();
  });

  it('clears and dispatches when the endpoint reports authenticated=false', async () => {
    authApiGet.mockResolvedValue({data: {authenticated: false}});
    const eventSpy = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventSpy);
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    await expect(bootstrapAuthSession()).resolves.toEqual({status: 'anonymous', session: null});

    expect(clearTokens).toHaveBeenCalledWith({generation: 'generation-a', refresh: 'refresh-token'});
    expect(eventSpy).toHaveBeenCalledTimes(1);
    window.removeEventListener('i2g-auth-state-change', eventSpy);
  });

  it('keeps the session verified when the payload has no usable member', async () => {
    authApiGet.mockResolvedValue({data: {user: {member_uuid: ''}}});
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    const result = await bootstrapAuthSession();

    expect(result).toMatchObject({status: 'verified', session: baseSession});
    expect(updateStoredSessionProfile).not.toHaveBeenCalled();
  });

  it('deduplicates concurrent bootstrap calls for one generation', async () => {
    let resolveGet!: (value: unknown) => void;
    authApiGet.mockReturnValue(
      new Promise((resolve) => {
        resolveGet = resolve;
      }),
    );
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    const first = bootstrapAuthSession();
    const second = bootstrapAuthSession();

    expect(authApiGet).toHaveBeenCalledTimes(1);
    resolveGet({data: {}});
    await expect(Promise.all([first, second])).resolves.toHaveLength(2);
  });

  it('returns a replacement session when the generation changes during a failed refresh', async () => {
    authApiGet.mockRejectedValue({response: {status: 503}});
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    const pending = bootstrapAuthSession();
    const replacement = {...baseSession, generation: 'generation-b', user: {...baseSession.user}};
    storedSession = replacement;

    await expect(pending).resolves.toEqual({status: 'unverified', session: replacement});
  });

  it('resolves anonymous when the session is cleared during a failed refresh', async () => {
    authApiGet.mockRejectedValue({response: {status: 503}});
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    const pending = bootstrapAuthSession();
    storedSession = null;

    await expect(pending).resolves.toEqual({status: 'anonymous', session: null});
  });

  it('keeps the session verified when the payload is not a usable object', async () => {
    authApiGet.mockResolvedValue({data: 'unexpected-string'});
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    const result = await bootstrapAuthSession();

    expect(result).toMatchObject({status: 'verified', session: baseSession});
    expect(updateStoredSessionProfile).not.toHaveBeenCalled();
  });

  it('computes a completed profile when no explicit flag is returned', async () => {
    authApiGet.mockResolvedValue({
      data: {
        user: {
          member_uuid: 'member-a',
          email: 'current@example.com',
          first_name: 'Ada',
          last_name: 'Lovelace',
          organization: 'Acme Corp',
        },
      },
    });
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    const result = await bootstrapAuthSession();

    expect(updateStoredSessionProfile).toHaveBeenCalledWith(
      {generation: 'generation-a', refresh: 'refresh-token'},
      expect.objectContaining({member_uuid: 'member-a'}),
      false,
    );
    expect(result).toMatchObject({status: 'verified'});
  });

  it('computes an incomplete profile when name fields are blank', async () => {
    authApiGet.mockResolvedValue({
      data: {
        user: {
          member_uuid: 'member-a',
          email: 'current@example.com',
          first_name: '',
          last_name: 'Lovelace',
          organization: 'Acme Corp',
        },
      },
    });
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    await bootstrapAuthSession();

    expect(updateStoredSessionProfile).toHaveBeenCalledWith(
      {generation: 'generation-a', refresh: 'refresh-token'},
      expect.anything(),
      true,
    );
  });

  it('returns a replacement session when the generation changes before verification', async () => {
    authApiGet.mockResolvedValue({data: {}});
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    const pending = bootstrapAuthSession();
    const replacement = {...baseSession, generation: 'generation-b', user: {...baseSession.user}};
    storedSession = replacement;

    await expect(pending).resolves.toEqual({status: 'unverified', session: replacement});
  });

  it('resolves anonymous when the session clears before verification', async () => {
    authApiGet.mockResolvedValue({data: {}});
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    const pending = bootstrapAuthSession();
    storedSession = null;

    await expect(pending).resolves.toEqual({status: 'anonymous', session: null});
  });

  it('does not dispatch when clearing tokens reports no change', async () => {
    clearTokens.mockReturnValue(false);
    authApiPost.mockResolvedValue({data: {}});
    const eventSpy = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventSpy);
    const {logout} = await import('@/features/auth/api/session');

    await logout();

    expect(clearTokens).toHaveBeenCalledWith({generation: 'generation-a', refresh: 'refresh-token'});
    expect(eventSpy).not.toHaveBeenCalled();
    window.removeEventListener('i2g-auth-state-change', eventSpy);
  });

  it('ignores a non-string optional profile field', async () => {
    authApiGet.mockResolvedValue({
      data: {
        user: {
          member_uuid: 'member-a',
          email: 'current@example.com',
          phone: 12345,
        },
      },
    });
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    await bootstrapAuthSession();

    const normalizedUser = updateStoredSessionProfile.mock.calls[0][1];
    expect(normalizedUser.phone).toBeUndefined();
  });

  it('prefers the nested completion flag from the user payload', async () => {
    authApiGet.mockResolvedValue({
      data: {
        user: {
          member_uuid: 'member-a',
          email: 'current@example.com',
          requires_profile_completion: true,
        },
      },
    });
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    await bootstrapAuthSession();

    expect(updateStoredSessionProfile).toHaveBeenCalledWith(
      {generation: 'generation-a', refresh: 'refresh-token'},
      expect.anything(),
      true,
    );
  });

  it('returns anonymous when the guarded clear reports no change', async () => {
    clearTokens.mockReturnValue(false);
    authApiGet.mockResolvedValue({data: {authenticated: false}});
    const eventSpy = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventSpy);
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    await expect(bootstrapAuthSession()).resolves.toEqual({status: 'anonymous', session: null});
    expect(eventSpy).not.toHaveBeenCalled();
    window.removeEventListener('i2g-auth-state-change', eventSpy);
  });

  it('resolves anonymous when the profile update cannot persist', async () => {
    authApiGet.mockResolvedValue({
      data: {
        user: {member_uuid: 'member-a', email: 'current@example.com'},
        requires_profile_completion: true,
      },
    });
    updateStoredSessionProfile.mockReturnValue(null);
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    await expect(bootstrapAuthSession()).resolves.toEqual({status: 'anonymous', session: null});
  });

  it('does not clear the in-flight marker owned by a newer generation', async () => {
    let resolveFirst!: (value: unknown) => void;
    const first = new Promise((resolve) => {
      resolveFirst = resolve;
    });
    let resolveSecond!: (value: unknown) => void;
    const second = new Promise((resolve) => {
      resolveSecond = resolve;
    });
    authApiGet.mockReturnValueOnce(first).mockReturnValueOnce(second);
    const {bootstrapAuthSession} = await import('@/features/auth/api/session');

    const firstBootstrap = bootstrapAuthSession();
    const replacement = {...baseSession, generation: 'generation-b', user: {...baseSession.user}};
    storedSession = replacement;
    const secondBootstrap = bootstrapAuthSession();

    resolveFirst({data: {}});
    await expect(firstBootstrap).resolves.toEqual({status: 'unverified', session: replacement});

    resolveSecond({data: {}});
    await expect(secondBootstrap).resolves.toMatchObject({status: 'verified'});
  });
});

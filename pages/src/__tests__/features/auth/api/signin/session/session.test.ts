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

  it('clears local state before an unresolved server logout', async () => {
    authApiPost.mockReturnValue(new Promise(() => undefined));
    const eventSpy = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventSpy);
    const {logout} = await import('@/features/auth/api/signin/session');

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
    const {logout} = await import('@/features/auth/api/signin/session');

    await logout();
    expect(callOrder).toEqual(['clearTokens', 'authApi.post']);
  });

  it('does not call the server when no session is stored', async () => {
    storedSession = null;
    const {logout} = await import('@/features/auth/api/signin/session');

    await logout();
    expect(clearTokens).toHaveBeenCalledWith(undefined);
    expect(authApiPost).not.toHaveBeenCalled();
  });

  it('swallows server logout errors after local state is cleared', async () => {
    authApiPost.mockRejectedValue(new Error('network down'));
    const {logout} = await import('@/features/auth/api/signin/session');

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
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

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
});

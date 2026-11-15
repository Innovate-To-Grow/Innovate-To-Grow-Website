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

  it('resolves anonymous when the session clears before verification', async () => {
    authApiGet.mockResolvedValue({data: {}});
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    const pending = bootstrapAuthSession();
    storedSession = null;

    await expect(pending).resolves.toEqual({status: 'anonymous', session: null});
  });

  it('does not dispatch when clearing tokens reports no change', async () => {
    clearTokens.mockReturnValue(false);
    authApiPost.mockResolvedValue({data: {}});
    const eventSpy = vi.fn();
    window.addEventListener('i2g-auth-state-change', eventSpy);
    const {logout} = await import('@/features/auth/api/signin/session');

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
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

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
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

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
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

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
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    await expect(bootstrapAuthSession()).resolves.toEqual({status: 'anonymous', session: null});
  });
});

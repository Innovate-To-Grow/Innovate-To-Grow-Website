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

  it('deduplicates concurrent bootstrap calls for one generation', async () => {
    let resolveGet!: (value: unknown) => void;
    authApiGet.mockReturnValue(
      new Promise((resolve) => {
        resolveGet = resolve;
      }),
    );
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    const first = bootstrapAuthSession();
    const second = bootstrapAuthSession();

    expect(authApiGet).toHaveBeenCalledTimes(1);
    resolveGet({data: {}});
    await expect(Promise.all([first, second])).resolves.toHaveLength(2);
  });

  it('returns a replacement session when the generation changes during a failed refresh', async () => {
    authApiGet.mockRejectedValue({response: {status: 503}});
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    const pending = bootstrapAuthSession();
    const replacement = {...baseSession, generation: 'generation-b', user: {...baseSession.user}};
    storedSession = replacement;

    await expect(pending).resolves.toEqual({status: 'unverified', session: replacement});
  });

  it('resolves anonymous when the session is cleared during a failed refresh', async () => {
    authApiGet.mockRejectedValue({response: {status: 503}});
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    const pending = bootstrapAuthSession();
    storedSession = null;

    await expect(pending).resolves.toEqual({status: 'anonymous', session: null});
  });

  it('keeps the session verified when the payload is not a usable object', async () => {
    authApiGet.mockResolvedValue({data: 'unexpected-string'});
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

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
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    const result = await bootstrapAuthSession();

    expect(updateStoredSessionProfile).toHaveBeenCalledWith(
      {generation: 'generation-a', refresh: 'refresh-token'},
      // The header's account button shows the name, so the stored user carries it.
      expect.objectContaining({member_uuid: 'member-a', first_name: 'Ada', last_name: 'Lovelace'}),
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
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    await bootstrapAuthSession();

    expect(updateStoredSessionProfile).toHaveBeenCalledWith(
      {generation: 'generation-a', refresh: 'refresh-token'},
      expect.anything(),
      true,
    );
  });

  it('returns a replacement session when the generation changes before verification', async () => {
    authApiGet.mockResolvedValue({data: {}});
    const {bootstrapAuthSession} = await import('@/features/auth/api/signin/session');

    const pending = bootstrapAuthSession();
    const replacement = {...baseSession, generation: 'generation-b', user: {...baseSession.user}};
    storedSession = replacement;

    await expect(pending).resolves.toEqual({status: 'unverified', session: replacement});
  });
});

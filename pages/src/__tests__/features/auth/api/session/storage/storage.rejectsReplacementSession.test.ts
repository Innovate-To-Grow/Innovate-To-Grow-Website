import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {User} from '@/features/auth/api/contracts/types';

const mockUser: User = {
  member_uuid: 'uuid-123',
  email: 'test@example.com',
  profile_image: 'img.png',
};

function createMockStorage(): Storage {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: vi.fn(() => { store = {}; }),
    get length() { return Object.keys(store).length; },
    key: vi.fn((i: number) => Object.keys(store)[i] ?? null),
  };
}

describe('storage', () => {
  let mockLocalStorage: Storage;
  let mockSessionStorage: Storage;

  beforeEach(() => {
    mockLocalStorage = createMockStorage();
    mockSessionStorage = createMockStorage();
    vi.stubGlobal('localStorage', mockLocalStorage);
    vi.stubGlobal('sessionStorage', mockSessionStorage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('rejects a replacement session when the atomic storage write fails', async () => {
    const {getStoredSession, persistAuthSession} = await import('@/features/auth/api/session/storage');
    const original = persistAuthSession({
      access: 'original-access',
      refresh: 'original-refresh',
      user: mockUser,
      requires_profile_completion: false,
    });
    vi.mocked(mockLocalStorage.setItem).mockImplementation(() => {
      throw new DOMException('Storage is unavailable', 'QuotaExceededError');
    });

    expect(() =>
      persistAuthSession({
        access: 'replacement-access',
        refresh: 'replacement-refresh',
        user: {
          ...mockUser,
          member_uuid: 'uuid-456',
          email: 'replacement@example.com',
        },
        requires_profile_completion: true,
      }),
    ).toThrow('Unable to persist the authentication session.');

    expect(getStoredSession()).toEqual(original);
  });

  it('reports an unwritable session with the typed error the login-link page relies on', async () => {
    const {persistAuthSession} = await import('@/features/auth/api/session/storage');
    const {SessionNotSavedError} = await import('@/features/auth/api/contracts/errors');
    vi.mocked(mockLocalStorage.setItem).mockImplementation(() => {
      throw new DOMException('Storage is unavailable', 'QuotaExceededError');
    });

    let thrown: unknown;
    try {
      persistAuthSession({
        access: 'blocked-access',
        refresh: 'blocked-refresh',
        user: mockUser,
        requires_profile_completion: false,
      });
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toBeInstanceOf(SessionNotSavedError);
    // Still an Error with the historical message, so existing catch sites match.
    expect(thrown).toBeInstanceOf(Error);
    expect((thrown as Error).message).toBe('Unable to persist the authentication session.');
  });

  it('migrates and removes a complete legacy session', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', JSON.stringify(mockUser));
    mockSessionStorage.setItem('i2g_profile_completion_required', 'true');

    const {getStoredSession} = await import('@/features/auth/api/session/storage');
    const session = getStoredSession();

    expect(session).toEqual(expect.objectContaining({
      version: 1,
      access: 'legacy-access',
      refresh: 'legacy-refresh',
      user: mockUser,
      requires_profile_completion: true,
      generation: expect.any(String),
    }));
    expect(mockLocalStorage.getItem('i2g_access_token')).toBeNull();
    expect(mockLocalStorage.getItem('i2g_refresh_token')).toBeNull();
    expect(mockLocalStorage.getItem('i2g_user')).toBeNull();
    expect(mockSessionStorage.getItem('i2g_profile_completion_required')).toBeNull();
  });

  it('rejects token updates and clears from an older generation', async () => {
    const {
      setTokens,
      updateSessionTokens,
      clearTokens,
      getStoredSession,
    } = await import('@/features/auth/api/session/storage');
    const oldSession = setTokens({access: 'old-a', refresh: 'old-r'}, mockUser);
    const currentSession = setTokens(
      {access: 'new-a', refresh: 'new-r'},
      {...mockUser, member_uuid: 'uuid-456', email: 'new@example.com'},
    );

    expect(updateSessionTokens(
      {generation: oldSession.generation, refresh: oldSession.refresh},
      {access: 'stale-a', refresh: 'stale-r'},
    )).toBeNull();
    expect(clearTokens({
      generation: oldSession.generation,
      refresh: oldSession.refresh,
    })).toBe(false);
    expect(getStoredSession()?.generation).toBe(currentSession.generation);
    expect(getStoredSession()?.access).toBe('new-a');
  });

  it('does not clear profile completion for a replacement generation', async () => {
    const {
      clearProfileCompletionRequired,
      getStoredSession,
      persistAuthSession,
    } = await import('@/features/auth/api/session/storage');
    const oldSession = persistAuthSession({
      access: 'old-a',
      refresh: 'old-r',
      user: mockUser,
      requires_profile_completion: true,
    });
    const replacement = persistAuthSession({
      access: 'new-a',
      refresh: 'new-r',
      user: {...mockUser, member_uuid: 'uuid-456', email: 'new@example.com'},
      requires_profile_completion: true,
    });

    expect(
      clearProfileCompletionRequired({
        generation: oldSession.generation,
        refresh: oldSession.refresh,
      }),
    ).toBe(false);
    expect(getStoredSession()?.generation).toBe(replacement.generation);
    expect(getStoredSession()?.requires_profile_completion).toBe(true);
  });

  it('falls back to a timestamp-based generation when crypto is unavailable', async () => {
    vi.stubGlobal('crypto', {});
    const {setTokens, getStoredSession} = await import('@/features/auth/api/session/storage');
    const session = setTokens({access: 'a', refresh: 'r'}, mockUser);
    expect(session.generation).toBeTruthy();
    expect(getStoredSession()?.generation).toBe(session.generation);
  });

  it('treats an unavailable localStorage read as an empty session', async () => {
    vi.mocked(mockLocalStorage.getItem).mockImplementation(() => {
      throw new DOMException('Storage is denied', 'SecurityError');
    });
    const {getStoredSession} = await import('@/features/auth/api/session/storage');
    expect(getStoredSession()).toBeNull();
  });
});

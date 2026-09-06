import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {User} from '@/features/auth/api/types';

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

  it('stores and retrieves tokens', async () => {
    const {setTokens, getAccessToken, getRefreshToken} = await import('@/features/auth/api/storage');
    setTokens({access: 'acc-token', refresh: 'ref-token'}, mockUser);
    expect(getAccessToken()).toBe('acc-token');
    expect(getRefreshToken()).toBe('ref-token');
  });

  it('returns null when no tokens stored', async () => {
    const {getAccessToken, getRefreshToken} = await import('@/features/auth/api/storage');
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it('clears all tokens', async () => {
    const {setTokens, clearTokens, getAccessToken, getRefreshToken, getStoredUser} = await import('@/features/auth/api/storage');
    setTokens({access: 'acc', refresh: 'ref'}, mockUser);
    clearTokens();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });

  it('stores and retrieves user', async () => {
    const {setTokens, getStoredUser} = await import('@/features/auth/api/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    const stored = getStoredUser();
    expect(stored).toEqual(mockUser);
  });

  it('returns null for invalid JSON user', async () => {
    mockLocalStorage.setItem('i2g_user', 'invalid json');
    const {getStoredUser} = await import('@/features/auth/api/storage');
    expect(getStoredUser()).toBeNull();
  });

  it('returns null when no user set', async () => {
    const {getStoredUser} = await import('@/features/auth/api/storage');
    expect(getStoredUser()).toBeNull();
  });

  it('updates user in storage', async () => {
    const {setTokens, updateStoredUser, getStoredUser} = await import('@/features/auth/api/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    updateStoredUser((user) => ({...user, email: 'updated@test.com'}));
    expect(getStoredUser()?.email).toBe('updated@test.com');
  });

  it('updateStoredUser does nothing when no user stored', async () => {
    const {updateStoredUser, getStoredUser} = await import('@/features/auth/api/storage');
    updateStoredUser((user) => ({...user, first_name: 'Updated'}));
    expect(getStoredUser()).toBeNull();
  });

  it('profile completion defaults to false', async () => {
    const {isProfileCompletionRequired} = await import('@/features/auth/api/storage');
    expect(isProfileCompletionRequired()).toBe(false);
  });

  it('sets profile completion to true', async () => {
    const {setTokens, setProfileCompletionRequired, isProfileCompletionRequired} = await import('@/features/auth/api/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    setProfileCompletionRequired(true);
    expect(isProfileCompletionRequired()).toBe(true);
  });

  it('clears profile completion when set to false', async () => {
    const {setTokens, setProfileCompletionRequired, isProfileCompletionRequired} = await import('@/features/auth/api/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    setProfileCompletionRequired(true);
    setProfileCompletionRequired(false);
    expect(isProfileCompletionRequired()).toBe(false);
  });

  it('persistAuthSession stores tokens and user', async () => {
    const {persistAuthSession, getAccessToken, getRefreshToken, getStoredUser, isProfileCompletionRequired} = await import('@/features/auth/api/storage');
    persistAuthSession({
      access: 'new-access',
      refresh: 'new-refresh',
      user: mockUser,
      requires_profile_completion: false,
    });
    expect(getAccessToken()).toBe('new-access');
    expect(getRefreshToken()).toBe('new-refresh');
    expect(getStoredUser()).toEqual(mockUser);
    expect(isProfileCompletionRequired()).toBe(false);
  });

  it('persistAuthSession sets profile completion flag', async () => {
    const {persistAuthSession, isProfileCompletionRequired} = await import('@/features/auth/api/storage');
    persistAuthSession({
      access: 'a',
      refresh: 'r',
      user: mockUser,
      requires_profile_completion: true,
    });
    expect(isProfileCompletionRequired()).toBe(true);
  });

  it('stores auth state in one versioned record', async () => {
    const {persistAuthSession} = await import('@/features/auth/api/storage');
    persistAuthSession({
      access: 'one-access',
      refresh: 'one-refresh',
      user: mockUser,
      requires_profile_completion: true,
    });

    const serialized = mockLocalStorage.getItem('i2g_auth_session');
    expect(serialized).not.toBeNull();
    expect(JSON.parse(serialized!)).toEqual(expect.objectContaining({
      version: 1,
      access: 'one-access',
      refresh: 'one-refresh',
      user: mockUser,
      requires_profile_completion: true,
      generation: expect.any(String),
    }));
    expect(mockLocalStorage.getItem('i2g_access_token')).toBeNull();
    expect(mockLocalStorage.getItem('i2g_refresh_token')).toBeNull();
    expect(mockLocalStorage.getItem('i2g_user')).toBeNull();
  });

  it('rejects a replacement session when the atomic storage write fails', async () => {
    const {getStoredSession, persistAuthSession} = await import('@/features/auth/api/storage');
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

  it('migrates and removes a complete legacy session', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', JSON.stringify(mockUser));
    mockSessionStorage.setItem('i2g_profile_completion_required', 'true');

    const {getStoredSession} = await import('@/features/auth/api/storage');
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
    } = await import('@/features/auth/api/storage');
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
    } = await import('@/features/auth/api/storage');
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
    const {setTokens, getStoredSession} = await import('@/features/auth/api/storage');
    const session = setTokens({access: 'a', refresh: 'r'}, mockUser);
    expect(session.generation).toBeTruthy();
    expect(getStoredSession()?.generation).toBe(session.generation);
  });

  it('treats an unavailable localStorage read as an empty session', async () => {
    vi.mocked(mockLocalStorage.getItem).mockImplementation(() => {
      throw new DOMException('Storage is denied', 'SecurityError');
    });
    const {getStoredSession} = await import('@/features/auth/api/storage');
    expect(getStoredSession()).toBeNull();
  });

  it('treats an unavailable sessionStorage read as no completion flag', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', JSON.stringify(mockUser));
    vi.mocked(mockSessionStorage.getItem).mockImplementation(() => {
      throw new DOMException('Storage is denied', 'SecurityError');
    });
    const {getStoredSession} = await import('@/features/auth/api/storage');
    const session = getStoredSession();
    expect(session).toEqual(expect.objectContaining({
      access: 'legacy-access',
      requires_profile_completion: false,
    }));
  });

  it('removes and ignores an unparseable session record', async () => {
    mockLocalStorage.setItem('i2g_auth_session', 'not-json');
    const {getStoredSession} = await import('@/features/auth/api/storage');
    expect(getStoredSession()).toBeNull();
    expect(mockLocalStorage.getItem('i2g_auth_session')).toBeNull();
  });

  it('ignores a stored session record that is not an object', async () => {
    mockLocalStorage.setItem('i2g_auth_session', JSON.stringify('just-a-string'));
    const {getStoredSession} = await import('@/features/auth/api/storage');
    expect(getStoredSession()).toBeNull();
    expect(mockLocalStorage.getItem('i2g_auth_session')).toBeNull();
  });

  it('removes incomplete legacy keys and returns null', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    const {getStoredSession} = await import('@/features/auth/api/storage');
    expect(getStoredSession()).toBeNull();
    expect(mockLocalStorage.getItem('i2g_access_token')).toBeNull();
  });

  it('removes legacy keys when the stored user is invalid JSON', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', 'invalid json');
    const {getStoredSession} = await import('@/features/auth/api/storage');
    expect(getStoredSession()).toBeNull();
    expect(mockLocalStorage.getItem('i2g_user')).toBeNull();
  });

  it('removes legacy keys when the stored user is not a valid user object', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', JSON.stringify('not-a-user'));
    const {getStoredSession} = await import('@/features/auth/api/storage');
    expect(getStoredSession()).toBeNull();
  });

  it('removes legacy keys when the stored user lacks an email or member uuid', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', JSON.stringify({email: 'x@y.com'}));
    const {getStoredSession} = await import('@/features/auth/api/storage');
    expect(getStoredSession()).toBeNull();
  });

  it('returns null when migrating a legacy session cannot be persisted', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', JSON.stringify(mockUser));
    vi.mocked(mockLocalStorage.setItem).mockImplementation(() => {
      throw new DOMException('Storage is full', 'QuotaExceededError');
    });
    const {getStoredSession} = await import('@/features/auth/api/storage');
    expect(getStoredSession()).toBeNull();
  });

  it('matches the current session only when generation and refresh agree', async () => {
    const {setTokens, isCurrentSession} = await import('@/features/auth/api/storage');
    const session = setTokens({access: 'a', refresh: 'r'}, mockUser);
    expect(isCurrentSession({generation: session.generation, refresh: 'r'})).toBe(true);
    expect(isCurrentSession({generation: session.generation, refresh: 'other'})).toBe(false);
    expect(isCurrentSession({generation: session.generation})).toBe(true);
    expect(isCurrentSession({generation: 'other'})).toBe(false);
  });

  it('cannot set profile completion when no session is stored', async () => {
    const {setProfileCompletionRequired} = await import('@/features/auth/api/storage');
    expect(setProfileCompletionRequired(true)).toBe(false);
  });

  it('clears profile completion and the legacy session flag on success', async () => {
    mockSessionStorage.setItem('i2g_profile_completion_required', 'true');
    const {
      setTokens,
      setProfileCompletionRequired,
      clearProfileCompletionRequired,
      isProfileCompletionRequired,
    } = await import('@/features/auth/api/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    setProfileCompletionRequired(true);

    expect(clearProfileCompletionRequired()).toBe(true);
    expect(isProfileCompletionRequired()).toBe(false);
    expect(mockSessionStorage.getItem('i2g_profile_completion_required')).toBeNull();
  });

  it('returns false when clearing profile completion cannot be persisted', async () => {
    const {setTokens, clearProfileCompletionRequired} = await import('@/features/auth/api/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    vi.mocked(mockLocalStorage.setItem).mockImplementation(() => {
      throw new DOMException('Storage is full', 'QuotaExceededError');
    });
    expect(clearProfileCompletionRequired()).toBe(false);
  });

  it('rotates access and refresh tokens for the current generation', async () => {
    const {setTokens, updateSessionTokens, getStoredSession} = await import('@/features/auth/api/storage');
    const session = setTokens({access: 'old-a', refresh: 'old-r'}, mockUser);
    const updated = updateSessionTokens(
      {generation: session.generation, refresh: 'old-r'},
      {access: 'new-a', refresh: 'new-r'},
    );
    expect(updated?.access).toBe('new-a');
    expect(updated?.refresh).toBe('new-r');
    expect(getStoredSession()?.access).toBe('new-a');
  });

  it('returns null when updating tokens cannot be persisted', async () => {
    const {setTokens, updateSessionTokens} = await import('@/features/auth/api/storage');
    const session = setTokens({access: 'old-a', refresh: 'old-r'}, mockUser);
    vi.mocked(mockLocalStorage.setItem).mockImplementation(() => {
      throw new DOMException('Storage is full', 'QuotaExceededError');
    });
    expect(
      updateSessionTokens(
        {generation: session.generation, refresh: 'old-r'},
        {access: 'new-a', refresh: 'new-r'},
      ),
    ).toBeNull();
  });

  it('updates the stored user and completion flag for the current generation', async () => {
    const {setTokens, updateStoredSessionProfile, getStoredSession} = await import('@/features/auth/api/storage');
    const session = setTokens({access: 'a', refresh: 'r'}, mockUser);
    const newUser = {...mockUser, email: 'updated@example.com'};
    const updated = updateStoredSessionProfile(
      {generation: session.generation, refresh: 'r'},
      newUser,
      true,
    );
    expect(updated?.user.email).toBe('updated@example.com');
    expect(updated?.requires_profile_completion).toBe(true);
    expect(getStoredSession()?.requires_profile_completion).toBe(true);
  });

  it('rejects a profile update for a mismatched generation', async () => {
    const {setTokens, updateStoredSessionProfile} = await import('@/features/auth/api/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    expect(
      updateStoredSessionProfile({generation: 'other', refresh: 'r'}, mockUser, false),
    ).toBeNull();
  });

  it('returns null when updating the profile cannot be persisted', async () => {
    const {setTokens, updateStoredSessionProfile} = await import('@/features/auth/api/storage');
    const session = setTokens({access: 'a', refresh: 'r'}, mockUser);
    vi.mocked(mockLocalStorage.setItem).mockImplementation(() => {
      throw new DOMException('Storage is full', 'QuotaExceededError');
    });
    expect(
      updateStoredSessionProfile({generation: session.generation, refresh: 'r'}, mockUser, false),
    ).toBeNull();
  });

  it('does not clear profile completion for a rotated refresh token', async () => {
    const {persistAuthSession, clearProfileCompletionRequired, getStoredSession} = await import('@/features/auth/api/storage');
    const session = persistAuthSession({
      access: 'a',
      refresh: 'r',
      user: mockUser,
      requires_profile_completion: true,
    });

    expect(clearProfileCompletionRequired({generation: session.generation, refresh: 'other'})).toBe(false);
    expect(getStoredSession()?.requires_profile_completion).toBe(true);
  });

  it('does not update the stored user for a mismatched generation', async () => {
    const {setTokens, updateStoredUser} = await import('@/features/auth/api/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);

    expect(
      updateStoredUser((user) => ({...user, email: 'x@y.com'}), 'other-generation'),
    ).toBeNull();
  });

  it('returns null when updating the stored user cannot be persisted', async () => {
    const {setTokens, updateStoredUser} = await import('@/features/auth/api/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    vi.mocked(mockLocalStorage.setItem).mockImplementation(() => {
      throw new DOMException('Storage is full', 'QuotaExceededError');
    });

    expect(updateStoredUser((user) => ({...user, email: 'x@y.com'}))).toBeNull();
  });

  it('does not clear tokens for a rotated refresh token', async () => {
    const {setTokens, clearTokens, getStoredSession} = await import('@/features/auth/api/storage');
    const session = setTokens({access: 'a', refresh: 'r'}, mockUser);

    expect(clearTokens({generation: session.generation, refresh: 'other'})).toBe(false);
    expect(getStoredSession()).not.toBeNull();
  });
});

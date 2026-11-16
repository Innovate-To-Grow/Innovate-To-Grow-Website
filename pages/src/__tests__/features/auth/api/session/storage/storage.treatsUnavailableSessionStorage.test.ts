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

  it('treats an unavailable sessionStorage read as no completion flag', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', JSON.stringify(mockUser));
    vi.mocked(mockSessionStorage.getItem).mockImplementation(() => {
      throw new DOMException('Storage is denied', 'SecurityError');
    });
    const {getStoredSession} = await import('@/features/auth/api/session/storage');
    const session = getStoredSession();
    expect(session).toEqual(expect.objectContaining({
      access: 'legacy-access',
      requires_profile_completion: false,
    }));
  });

  it('removes and ignores an unparseable session record', async () => {
    mockLocalStorage.setItem('i2g_auth_session', 'not-json');
    const {getStoredSession} = await import('@/features/auth/api/session/storage');
    expect(getStoredSession()).toBeNull();
    expect(mockLocalStorage.getItem('i2g_auth_session')).toBeNull();
  });

  it('ignores a stored session record that is not an object', async () => {
    mockLocalStorage.setItem('i2g_auth_session', JSON.stringify('just-a-string'));
    const {getStoredSession} = await import('@/features/auth/api/session/storage');
    expect(getStoredSession()).toBeNull();
    expect(mockLocalStorage.getItem('i2g_auth_session')).toBeNull();
  });

  it('removes incomplete legacy keys and returns null', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    const {getStoredSession} = await import('@/features/auth/api/session/storage');
    expect(getStoredSession()).toBeNull();
    expect(mockLocalStorage.getItem('i2g_access_token')).toBeNull();
  });

  it('removes legacy keys when the stored user is invalid JSON', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', 'invalid json');
    const {getStoredSession} = await import('@/features/auth/api/session/storage');
    expect(getStoredSession()).toBeNull();
    expect(mockLocalStorage.getItem('i2g_user')).toBeNull();
  });

  it('removes legacy keys when the stored user is not a valid user object', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', JSON.stringify('not-a-user'));
    const {getStoredSession} = await import('@/features/auth/api/session/storage');
    expect(getStoredSession()).toBeNull();
  });

  it('removes legacy keys when the stored user lacks an email or member uuid', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', JSON.stringify({email: 'x@y.com'}));
    const {getStoredSession} = await import('@/features/auth/api/session/storage');
    expect(getStoredSession()).toBeNull();
  });

  it('returns null when migrating a legacy session cannot be persisted', async () => {
    mockLocalStorage.setItem('i2g_access_token', 'legacy-access');
    mockLocalStorage.setItem('i2g_refresh_token', 'legacy-refresh');
    mockLocalStorage.setItem('i2g_user', JSON.stringify(mockUser));
    vi.mocked(mockLocalStorage.setItem).mockImplementation(() => {
      throw new DOMException('Storage is full', 'QuotaExceededError');
    });
    const {getStoredSession} = await import('@/features/auth/api/session/storage');
    expect(getStoredSession()).toBeNull();
  });

  it('matches the current session only when generation and refresh agree', async () => {
    const {setTokens, isCurrentSession} = await import('@/features/auth/api/session/storage');
    const session = setTokens({access: 'a', refresh: 'r'}, mockUser);
    expect(isCurrentSession({generation: session.generation, refresh: 'r'})).toBe(true);
    expect(isCurrentSession({generation: session.generation, refresh: 'other'})).toBe(false);
    expect(isCurrentSession({generation: session.generation})).toBe(true);
    expect(isCurrentSession({generation: 'other'})).toBe(false);
  });

  it('cannot set profile completion when no session is stored', async () => {
    const {setProfileCompletionRequired} = await import('@/features/auth/api/session/storage');
    expect(setProfileCompletionRequired(true)).toBe(false);
  });

  it('clears profile completion and the legacy session flag on success', async () => {
    mockSessionStorage.setItem('i2g_profile_completion_required', 'true');
    const {
      setTokens,
      setProfileCompletionRequired,
      clearProfileCompletionRequired,
      isProfileCompletionRequired,
    } = await import('@/features/auth/api/session/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    setProfileCompletionRequired(true);

    expect(clearProfileCompletionRequired()).toBe(true);
    expect(isProfileCompletionRequired()).toBe(false);
    expect(mockSessionStorage.getItem('i2g_profile_completion_required')).toBeNull();
  });

  it('returns false when clearing profile completion cannot be persisted', async () => {
    const {setTokens, setProfileCompletionRequired, clearProfileCompletionRequired} = await import('@/features/auth/api/session/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    setProfileCompletionRequired(true);
    vi.mocked(mockLocalStorage.setItem).mockImplementation(() => {
      throw new DOMException('Storage is full', 'QuotaExceededError');
    });
    expect(clearProfileCompletionRequired()).toBe(false);
  });

  it('rotates access and refresh tokens for the current generation', async () => {
    const {setTokens, updateSessionTokens, getStoredSession} = await import('@/features/auth/api/session/storage');
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
    const {setTokens, updateSessionTokens} = await import('@/features/auth/api/session/storage');
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
    const {setTokens, updateStoredSessionProfile, getStoredSession} = await import('@/features/auth/api/session/storage');
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
});

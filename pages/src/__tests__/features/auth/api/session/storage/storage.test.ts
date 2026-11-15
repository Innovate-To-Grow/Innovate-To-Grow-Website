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

  it('stores and retrieves tokens', async () => {
    const {setTokens, getAccessToken, getRefreshToken} = await import('@/features/auth/api/session/storage');
    setTokens({access: 'acc-token', refresh: 'ref-token'}, mockUser);
    expect(getAccessToken()).toBe('acc-token');
    expect(getRefreshToken()).toBe('ref-token');
  });

  it('returns null when no tokens stored', async () => {
    const {getAccessToken, getRefreshToken} = await import('@/features/auth/api/session/storage');
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it('clears all tokens', async () => {
    const {setTokens, clearTokens, getAccessToken, getRefreshToken, getStoredUser} = await import('@/features/auth/api/session/storage');
    setTokens({access: 'acc', refresh: 'ref'}, mockUser);
    clearTokens();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });

  it('stores and retrieves user', async () => {
    const {setTokens, getStoredUser} = await import('@/features/auth/api/session/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    const stored = getStoredUser();
    expect(stored).toEqual(mockUser);
  });

  it('returns null for invalid JSON user', async () => {
    mockLocalStorage.setItem('i2g_user', 'invalid json');
    const {getStoredUser} = await import('@/features/auth/api/session/storage');
    expect(getStoredUser()).toBeNull();
  });

  it('returns null when no user set', async () => {
    const {getStoredUser} = await import('@/features/auth/api/session/storage');
    expect(getStoredUser()).toBeNull();
  });

  it('updates user in storage', async () => {
    const {setTokens, updateStoredUser, getStoredUser} = await import('@/features/auth/api/session/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    updateStoredUser((user) => ({...user, email: 'updated@test.com'}));
    expect(getStoredUser()?.email).toBe('updated@test.com');
  });

  it('keeps null and omitted profile images identical across session and profile updates', async () => {
    const {setTokens, getStoredSession, updateStoredUser, updateStoredSessionProfile} = await import('@/features/auth/api/session/storage');
    const withoutImage = {...mockUser, profile_image: null} as unknown as User;
    const session = setTokens({access: 'a', refresh: 'r'}, withoutImage);
    const original = mockLocalStorage.getItem('i2g_auth_session');
    vi.mocked(mockLocalStorage.setItem).mockClear();

    for (let cycle = 0; cycle < 3; cycle += 1) {
      updateStoredSessionProfile(session, {...mockUser, profile_image: undefined}, false);
      const updatedUser = updateStoredUser((user) => ({...user, profile_image: null}) as unknown as User, session.generation);
      expect(updatedUser).not.toHaveProperty('profile_image');
      expect(mockLocalStorage.getItem('i2g_auth_session')).toBe(original);
    }
    expect(getStoredSession()?.user).not.toHaveProperty('profile_image');
    expect(mockLocalStorage.setItem).not.toHaveBeenCalled();
  });

  it('normalizes old null images on read and persists real image changes', async () => {
    const {setTokens, getStoredSession, updateStoredUser} = await import('@/features/auth/api/session/storage');
    const session = setTokens({access: 'a', refresh: 'r'}, mockUser);
    mockLocalStorage.setItem('i2g_auth_session', JSON.stringify({...session, user: {...mockUser, profile_image: null}}));
    expect(getStoredSession()?.user).not.toHaveProperty('profile_image');
    updateStoredUser((user) => ({...user, profile_image: '/new-avatar.png'}));
    expect(getStoredSession()?.user.profile_image).toBe('/new-avatar.png');
  });

  it('updateStoredUser does nothing when no user stored', async () => {
    const {updateStoredUser, getStoredUser} = await import('@/features/auth/api/session/storage');
    updateStoredUser((user) => ({...user, first_name: 'Updated'}));
    expect(getStoredUser()).toBeNull();
  });

  it('profile completion defaults to false', async () => {
    const {isProfileCompletionRequired} = await import('@/features/auth/api/session/storage');
    expect(isProfileCompletionRequired()).toBe(false);
  });

  it('sets profile completion to true', async () => {
    const {setTokens, setProfileCompletionRequired, isProfileCompletionRequired} = await import('@/features/auth/api/session/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    setProfileCompletionRequired(true);
    expect(isProfileCompletionRequired()).toBe(true);
  });

  it('clears profile completion when set to false', async () => {
    const {setTokens, setProfileCompletionRequired, isProfileCompletionRequired} = await import('@/features/auth/api/session/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    setProfileCompletionRequired(true);
    setProfileCompletionRequired(false);
    expect(isProfileCompletionRequired()).toBe(false);
  });

  it('persistAuthSession stores tokens and user', async () => {
    const {persistAuthSession, getAccessToken, getRefreshToken, getStoredUser, isProfileCompletionRequired} = await import('@/features/auth/api/session/storage');
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
    const {persistAuthSession, isProfileCompletionRequired} = await import('@/features/auth/api/session/storage');
    persistAuthSession({
      access: 'a',
      refresh: 'r',
      user: mockUser,
      requires_profile_completion: true,
    });
    expect(isProfileCompletionRequired()).toBe(true);
  });

  it('stores auth state in one versioned record', async () => {
    const {persistAuthSession} = await import('@/features/auth/api/session/storage');
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
});

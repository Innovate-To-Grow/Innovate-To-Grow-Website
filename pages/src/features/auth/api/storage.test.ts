import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type {User} from './types';

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
    const {setTokens, getAccessToken, getRefreshToken} = await import('./storage');
    setTokens({access: 'acc-token', refresh: 'ref-token'}, mockUser);
    expect(getAccessToken()).toBe('acc-token');
    expect(getRefreshToken()).toBe('ref-token');
  });

  it('returns null when no tokens stored', async () => {
    const {getAccessToken, getRefreshToken} = await import('./storage');
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it('clears all tokens', async () => {
    const {setTokens, clearTokens, getAccessToken, getRefreshToken, getStoredUser} = await import('./storage');
    setTokens({access: 'acc', refresh: 'ref'}, mockUser);
    clearTokens();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });

  it('stores and retrieves user', async () => {
    const {setTokens, getStoredUser} = await import('./storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    const stored = getStoredUser();
    expect(stored).toEqual(mockUser);
  });

  it('returns null for invalid JSON user', async () => {
    mockLocalStorage.setItem('i2g_user', 'invalid json');
    const {getStoredUser} = await import('./storage');
    expect(getStoredUser()).toBeNull();
  });

  it('returns null when no user set', async () => {
    const {getStoredUser} = await import('./storage');
    expect(getStoredUser()).toBeNull();
  });

  it('updates user in storage', async () => {
    const {setTokens, updateStoredUser, getStoredUser} = await import('./storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    updateStoredUser((user) => ({...user, email: 'updated@test.com'}));
    expect(getStoredUser()?.email).toBe('updated@test.com');
  });

  it('updateStoredUser does nothing when no user stored', async () => {
    const {updateStoredUser, getStoredUser} = await import('./storage');
    updateStoredUser((user) => ({...user, first_name: 'Updated'}));
    expect(getStoredUser()).toBeNull();
  });

  it('profile completion defaults to false', async () => {
    const {isProfileCompletionRequired} = await import('./storage');
    expect(isProfileCompletionRequired()).toBe(false);
  });

  it('sets profile completion to true', async () => {
    const {setProfileCompletionRequired, isProfileCompletionRequired} = await import('./storage');
    setProfileCompletionRequired(true);
    expect(isProfileCompletionRequired()).toBe(true);
  });

  it('clears profile completion when set to false', async () => {
    const {setProfileCompletionRequired, isProfileCompletionRequired} = await import('./storage');
    setProfileCompletionRequired(true);
    setProfileCompletionRequired(false);
    expect(isProfileCompletionRequired()).toBe(false);
  });

  it('persistAuthSession stores tokens and user', async () => {
    const {persistAuthSession, getAccessToken, getRefreshToken, getStoredUser, isProfileCompletionRequired} = await import('./storage');
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
    const {persistAuthSession, isProfileCompletionRequired} = await import('./storage');
    persistAuthSession({
      access: 'a',
      refresh: 'r',
      user: mockUser,
      requires_profile_completion: true,
    });
    expect(isProfileCompletionRequired()).toBe(true);
  });
});

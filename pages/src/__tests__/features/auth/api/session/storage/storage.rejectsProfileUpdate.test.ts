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

  it('rejects a profile update for a mismatched generation', async () => {
    const {setTokens, updateStoredSessionProfile} = await import('@/features/auth/api/session/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    expect(
      updateStoredSessionProfile({generation: 'other', refresh: 'r'}, mockUser, false),
    ).toBeNull();
  });

  it('returns null when updating the profile cannot be persisted', async () => {
    const {setTokens, updateStoredSessionProfile} = await import('@/features/auth/api/session/storage');
    const session = setTokens({access: 'a', refresh: 'r'}, mockUser);
    vi.mocked(mockLocalStorage.setItem).mockImplementation(() => {
      throw new DOMException('Storage is full', 'QuotaExceededError');
    });
    expect(
      updateStoredSessionProfile({generation: session.generation, refresh: 'r'}, mockUser, true),
    ).toBeNull();
  });

  it('does not clear profile completion for a rotated refresh token', async () => {
    const {persistAuthSession, clearProfileCompletionRequired, getStoredSession} = await import('@/features/auth/api/session/storage');
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
    const {setTokens, updateStoredUser} = await import('@/features/auth/api/session/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);

    expect(
      updateStoredUser((user) => ({...user, email: 'x@y.com'}), 'other-generation'),
    ).toBeNull();
  });

  it('returns null when updating the stored user cannot be persisted', async () => {
    const {setTokens, updateStoredUser} = await import('@/features/auth/api/session/storage');
    setTokens({access: 'a', refresh: 'r'}, mockUser);
    vi.mocked(mockLocalStorage.setItem).mockImplementation(() => {
      throw new DOMException('Storage is full', 'QuotaExceededError');
    });

    expect(updateStoredUser((user) => ({...user, email: 'x@y.com'}))).toBeNull();
  });

  it('does not clear tokens for a rotated refresh token', async () => {
    const {setTokens, clearTokens, getStoredSession} = await import('@/features/auth/api/session/storage');
    const session = setTokens({access: 'a', refresh: 'r'}, mockUser);

    expect(clearTokens({generation: session.generation, refresh: 'other'})).toBe(false);
    expect(getStoredSession()).not.toBeNull();
  });
});

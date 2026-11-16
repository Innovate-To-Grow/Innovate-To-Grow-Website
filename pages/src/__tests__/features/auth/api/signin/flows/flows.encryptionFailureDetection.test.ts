import {beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  encrypt: vi.fn(),
  clearKeyCache: vi.fn(),
  persist: vi.fn(),
  clearProfileCompletion: vi.fn(),
}));

vi.mock('@/features/auth/api/session/client', () => ({
  authApi: {post: mocks.post},
}));

vi.mock('@/lib/security', () => ({
  encryptPasswordWithCurrentKey: mocks.encrypt,
  clearKeyCache: mocks.clearKeyCache,
}));

vi.mock('@/features/auth/api/session/storage', () => ({
  persistAuthSession: mocks.persist,
  clearProfileCompletionRequired: mocks.clearProfileCompletion,
}));

vi.mock('axios', () => ({
  default: {isAxiosError: (e: unknown) => e && typeof e === 'object' && 'isAxiosError' in e},
  isAxiosError: (e: unknown) => e && typeof e === 'object' && 'isAxiosError' in e,
}));

import {
  login,
  register,
} from '@/features/auth/api/signin/flows';

describe('auth flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mocks.encrypt.mockResolvedValue({encryptedPassword: 'enc-pw', keyId: 'key-1'});
  });

  describe('encryption failure detection', () => {
    it('clears the key cache for a non-axios error', async () => {
      mocks.post.mockRejectedValue(new Error('crypto failure'));

      await expect(login('a@b.com', 'pw')).rejects.toBeDefined();
      expect(mocks.clearKeyCache).toHaveBeenCalled();
    });

    it('does not clear the key cache for a falsy rejection', async () => {
      mocks.post.mockRejectedValue(null);

      await expect(login('a@b.com', 'pw')).rejects.toBeNull();
      expect(mocks.clearKeyCache).not.toHaveBeenCalled();
    });

    it('clears the key cache for an axios error with an object payload mentioning the key', async () => {
      const axiosError = {isAxiosError: true, response: {data: {key_id: 'stale-key'}}};
      mocks.post.mockRejectedValue(axiosError);

      await expect(register('a@b.com', 'pw', 'pw', 'F', 'L', 'O')).rejects.toBeDefined();
      expect(mocks.clearKeyCache).toHaveBeenCalled();
    });

    it('does not clear the key cache for an axios error without matching content', async () => {
      const axiosError = {isAxiosError: true, response: {}};
      mocks.post.mockRejectedValue(axiosError);

      await expect(register('a@b.com', 'pw', 'pw', 'F', 'L', 'O')).rejects.toBeDefined();
      expect(mocks.clearKeyCache).not.toHaveBeenCalled();
    });
  });
});

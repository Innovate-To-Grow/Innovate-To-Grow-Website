import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('../shared/api/client', () => ({
  api: {get: mocks.get},
}));

import {clearKeyCache, fetchPublicKey} from './crypto';

const FAKE_PEM = '-----BEGIN PUBLIC KEY-----\nMIIBfake\n-----END PUBLIC KEY-----';

describe('crypto', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearKeyCache();
  });

  afterEach(() => {
    clearKeyCache();
  });

  describe('fetchPublicKey', () => {
    it('fetches key from server', async () => {
      mocks.get.mockResolvedValue({data: {public_key: FAKE_PEM, key_id: 'k1'}});

      const result = await fetchPublicKey();
      expect(mocks.get).toHaveBeenCalledWith('/authn/public-key/');
      expect(result.publicKey).toBe(FAKE_PEM);
      expect(result.keyId).toBe('k1');
    });

    it('caches subsequent calls', async () => {
      mocks.get.mockResolvedValue({data: {public_key: FAKE_PEM, key_id: 'k1'}});

      await fetchPublicKey();
      await fetchPublicKey();
      expect(mocks.get).toHaveBeenCalledTimes(1);
    });

    it('re-fetches after cache clear', async () => {
      mocks.get.mockResolvedValue({data: {public_key: FAKE_PEM, key_id: 'k1'}});

      await fetchPublicKey();
      clearKeyCache();
      await fetchPublicKey();
      expect(mocks.get).toHaveBeenCalledTimes(2);
    });

    it('deduplicates concurrent requests', async () => {
      mocks.get.mockResolvedValue({data: {public_key: FAKE_PEM, key_id: 'k1'}});

      const [a, b] = await Promise.all([fetchPublicKey(), fetchPublicKey()]);
      expect(mocks.get).toHaveBeenCalledTimes(1);
      expect(a).toEqual(b);
    });
  });
});

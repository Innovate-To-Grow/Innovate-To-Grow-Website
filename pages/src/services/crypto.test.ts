import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import crypto from 'node:crypto';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('../shared/api/client', () => ({
  api: {get: mocks.get},
}));

import {clearKeyCache, encryptPasswordWithCurrentKey, fetchPublicKey} from './crypto';

function generateTestKeyPem(): string {
  const {publicKey} = crypto.generateKeyPairSync('rsa', {
    modulusLength: 2048,
    publicKeyEncoding: {type: 'spki', format: 'pem'},
    privateKeyEncoding: {type: 'pkcs8', format: 'pem'},
  });
  return publicKey;
}

describe('crypto', () => {
  let testPem: string;

  beforeEach(() => {
    vi.clearAllMocks();
    clearKeyCache();
    testPem = generateTestKeyPem();
  });

  afterEach(() => {
    clearKeyCache();
  });

  describe('fetchPublicKey', () => {
    it('fetches key from server', async () => {
      mocks.get.mockResolvedValue({data: {public_key: testPem, key_id: 'k1'}});

      const result = await fetchPublicKey();
      expect(mocks.get).toHaveBeenCalledWith('/authn/public-key/');
      expect(result.publicKey).toBe(testPem);
      expect(result.keyId).toBe('k1');
    });

    it('caches subsequent calls', async () => {
      mocks.get.mockResolvedValue({data: {public_key: testPem, key_id: 'k1'}});

      await fetchPublicKey();
      await fetchPublicKey();
      expect(mocks.get).toHaveBeenCalledTimes(1);
    });

    it('re-fetches after cache clear', async () => {
      mocks.get.mockResolvedValue({data: {public_key: testPem, key_id: 'k1'}});

      await fetchPublicKey();
      clearKeyCache();
      await fetchPublicKey();
      expect(mocks.get).toHaveBeenCalledTimes(2);
    });
  });

  describe('encryptPasswordWithCurrentKey', () => {
    it('returns encrypted password and key id', async () => {
      mocks.get.mockResolvedValue({data: {public_key: testPem, key_id: 'key-42'}});

      const result = await encryptPasswordWithCurrentKey('pw123');
      expect(result.keyId).toBe('key-42');
      expect(result.encryptedPassword.length).toBeGreaterThan(0);
      expect(result.encryptedPassword).toMatch(/^[A-Za-z0-9+/]+=*$/);
    });

    it('produces different ciphertext each call (OAEP padding)', async () => {
      mocks.get.mockResolvedValue({data: {public_key: testPem, key_id: 'key-1'}});

      const a = await encryptPasswordWithCurrentKey('same');
      clearKeyCache();
      mocks.get.mockResolvedValue({data: {public_key: testPem, key_id: 'key-1'}});
      const b = await encryptPasswordWithCurrentKey('same');
      expect(a.encryptedPassword).not.toBe(b.encryptedPassword);
    });
  });
});

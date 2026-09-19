import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: {get: mocks.get},
}));

import {
  clearKeyCache,
  encryptPassword,
  encryptPasswordWithCurrentKey,
  fetchPublicKey,
} from '@/lib/security/crypto';

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

  describe('encryptPasswordWithCurrentKey', () => {
    const subtleImportKey = vi.fn();
    const subtleEncrypt = vi.fn();

    beforeEach(() => {
      subtleImportKey.mockReset();
      subtleEncrypt.mockReset();
      subtleImportKey.mockResolvedValue({type: 'public'});
      subtleEncrypt.mockResolvedValue(new Uint8Array([1, 2, 3]).buffer);
      vi.stubGlobal('crypto', {
        subtle: {
          importKey: subtleImportKey,
          encrypt: subtleEncrypt,
        },
      });
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('encrypts a password with the current public key', async () => {
      mocks.get.mockResolvedValue({data: {public_key: FAKE_PEM, key_id: 'k1'}});

      const result = await encryptPasswordWithCurrentKey('hunter2');

      expect(result.keyId).toBe('k1');
      expect(result.encryptedPassword).toBe(btoa('\x01\x02\x03'));
      expect(subtleEncrypt).toHaveBeenCalledTimes(1);
    });

    it('imports the PEM body as an SPKI RSA-OAEP key before encrypting', async () => {
      const result = await encryptPassword('secret', FAKE_PEM);

      expect(subtleImportKey).toHaveBeenCalledWith(
        'spki',
        expect.any(ArrayBuffer),
        {name: 'RSA-OAEP', hash: 'SHA-256'},
        false,
        ['encrypt'],
      );
      expect(subtleEncrypt).toHaveBeenCalledWith(
        {name: 'RSA-OAEP'},
        {type: 'public'},
        expect.anything(),
      );
      const receivedBytes = Array.from(subtleEncrypt.mock.calls[0][2] as Uint8Array);
      expect(receivedBytes).toEqual(Array.from(new TextEncoder().encode('secret')));
      expect(result).toBe(btoa('\x01\x02\x03'));
    });
  });
});

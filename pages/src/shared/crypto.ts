import { api } from './api/client';

interface PublicKeyResponse {
  public_key: string;
  key_id: string;
}

interface CachedKey {
  publicKey: string;
  keyId: string;
  fetchedAt: number;
}

const KEY_CACHE_DURATION = 5 * 60 * 1000;
let cachedKey: CachedKey | null = null;
let inFlight: Promise<{ publicKey: string; keyId: string }> | null = null;

export const fetchPublicKey = async (): Promise<{ publicKey: string; keyId: string }> => {
  if (cachedKey && Date.now() - cachedKey.fetchedAt < KEY_CACHE_DURATION) {
    return { publicKey: cachedKey.publicKey, keyId: cachedKey.keyId };
  }

  if (inFlight) return inFlight;

  inFlight = (async () => {
    try {
      const response = await api.get<PublicKeyResponse>('/authn/public-key/');
      cachedKey = {
        publicKey: response.data.public_key,
        keyId: response.data.key_id,
        fetchedAt: Date.now(),
      };
      return { publicKey: cachedKey.publicKey, keyId: cachedKey.keyId };
    } finally {
      inFlight = null;
    }
  })();

  return inFlight;
};

export const clearKeyCache = (): void => {
  cachedKey = null;
};

const pemToPublicKey = async (pem: string): Promise<CryptoKey> => {
  const pemContents = pem
    .replace(/-----BEGIN PUBLIC KEY-----/, '')
    .replace(/-----END PUBLIC KEY-----/, '')
    .replace(/\s/g, '');

  const binaryDer = Uint8Array.from(atob(pemContents), c => c.charCodeAt(0));

  return await crypto.subtle.importKey(
    'spki',
    binaryDer.buffer,
    {
      name: 'RSA-OAEP',
      hash: 'SHA-256',
    },
    false,
    ['encrypt']
  );
};

export const encryptPassword = async (
  password: string,
  publicKeyPem: string
): Promise<string> => {
  const publicKey = await pemToPublicKey(publicKeyPem);

  const encoder = new TextEncoder();
  const passwordBytes = encoder.encode(password);

  const encryptedBuffer = await crypto.subtle.encrypt(
    {
      name: 'RSA-OAEP',
    },
    publicKey,
    passwordBytes
  );

  const encryptedBytes = new Uint8Array(encryptedBuffer);
  let binary = '';
  for (let i = 0; i < encryptedBytes.byteLength; i++) {
    binary += String.fromCharCode(encryptedBytes[i]);
  }
  return btoa(binary);
};

export const encryptPasswordWithCurrentKey = async (
  password: string
): Promise<{ encryptedPassword: string; keyId: string }> => {
  const { publicKey, keyId } = await fetchPublicKey();
  const encryptedPassword = await encryptPassword(password, publicKey);
  return { encryptedPassword, keyId };
};

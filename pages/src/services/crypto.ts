/**
 * RSA encryption utilities for secure password transmission.
 */

import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

// ======================== Types ========================

interface PublicKeyResponse {
  public_key: string;
  key_id: string;
}

interface CachedKey {
  publicKey: string;
  keyId: string;
  fetchedAt: number;
}

// ======================== Key Cache ========================

// Cache key for 5 minutes to reduce API calls
const KEY_CACHE_DURATION = 5 * 60 * 1000;
let cachedKey: CachedKey | null = null;

/**
 * Fetch the current public key from the server.
 */
export const fetchPublicKey = async (): Promise<{ publicKey: string; keyId: string }> => {
  // Check if we have a valid cached key
  if (cachedKey && Date.now() - cachedKey.fetchedAt < KEY_CACHE_DURATION) {
    return { publicKey: cachedKey.publicKey, keyId: cachedKey.keyId };
  }

  // Fetch new key from server
  const response = await axios.get<PublicKeyResponse>(`${API_BASE_URL}/authn/public-key/`);
  
  // Cache the key
  cachedKey = {
    publicKey: response.data.public_key,
    keyId: response.data.key_id,
    fetchedAt: Date.now(),
  };

  return { publicKey: cachedKey.publicKey, keyId: cachedKey.keyId };
};

/**
 * Clear the cached public key (call this on key rotation errors).
 */
export const clearKeyCache = (): void => {
  cachedKey = null;
};

// ======================== RSA Encryption ========================

/**
 * Convert a PEM public key to a CryptoKey for use with Web Crypto API.
 */
const pemToPublicKey = async (pem: string): Promise<CryptoKey> => {
  // Remove PEM headers and decode base64
  const pemContents = pem
    .replace(/-----BEGIN PUBLIC KEY-----/, '')
    .replace(/-----END PUBLIC KEY-----/, '')
    .replace(/\s/g, '');
  
  const binaryDer = Uint8Array.from(atob(pemContents), c => c.charCodeAt(0));

  // Import the key
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

/**
 * Encrypt a password using RSA-OAEP with the provided public key.
 * Returns base64-encoded encrypted data.
 */
export const encryptPassword = async (
  password: string,
  publicKeyPem: string
): Promise<string> => {
  // Convert PEM to CryptoKey
  const publicKey = await pemToPublicKey(publicKeyPem);

  // Encode password as UTF-8 bytes
  const encoder = new TextEncoder();
  const passwordBytes = encoder.encode(password);

  // Encrypt using RSA-OAEP
  const encryptedBuffer = await crypto.subtle.encrypt(
    {
      name: 'RSA-OAEP',
    },
    publicKey,
    passwordBytes
  );

  // Convert to base64
  const encryptedBytes = new Uint8Array(encryptedBuffer);
  let binary = '';
  for (let i = 0; i < encryptedBytes.byteLength; i++) {
    binary += String.fromCharCode(encryptedBytes[i]);
  }
  return btoa(binary);
};

/**
 * Encrypt a password using the current server public key.
 * Returns the encrypted password and the key ID used.
 */
export const encryptPasswordWithCurrentKey = async (
  password: string
): Promise<{ encryptedPassword: string; keyId: string }> => {
  const { publicKey, keyId } = await fetchPublicKey();
  const encryptedPassword = await encryptPassword(password, publicKey);
  return { encryptedPassword, keyId };
};


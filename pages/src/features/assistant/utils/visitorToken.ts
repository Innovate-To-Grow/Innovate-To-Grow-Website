/**
 * The assistant's visitor token: a server-signed, opaque value that tells the
 * backend "this is one browser". The backend keys its per-visitor limits on it
 * instead of the client IP, because the whole campus shares one public IP.
 *
 * It is not a credential and grants nothing; it only gives this browser its own
 * rate/usage bucket. The backend hands one out with `GET /assistant/config/`
 * and may hand back a replacement with any chat response (when the one we sent
 * was missing, expired or otherwise not accepted, or is due for renewal).
 */

/** localStorage key holding the token, so the identity survives reloads. */
const STORAGE_KEY = 'itg-assistant-visitor';

/** A genuine token is ~110 characters; never store or send anything absurd. */
const MAX_TOKEN_CHARS = 512;

/**
 * In-memory fallback used when localStorage is unavailable (e.g. Safari
 * private mode throws on access). Keeps the identity stable within the tab.
 */
let memoryToken: string | null = null;

function isUsableToken(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= MAX_TOKEN_CHARS;
}

/** The token to send with a chat request, or null when none is held yet. */
export function getVisitorToken(): string | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isUsableToken(stored)) return stored;
  } catch {
    /* storage unavailable: fall through to the in-memory copy */
  }
  return memoryToken;
}

/**
 * Replace the held token with one the backend told us to use. Anything that
 * is not a plausible token is ignored, so a malformed response can never wipe
 * a working identity.
 */
export function storeVisitorToken(token: unknown): void {
  if (!isUsableToken(token)) return;
  memoryToken = token;
  try {
    localStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Privacy mode or quota: the in-memory copy serves this tab. Reads prefer
    // storage, so drop any older stored token too, or it would keep shadowing
    // the replacement we could not write.
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* storage fully unavailable; reads fall back to memory anyway */
    }
  }
}

/**
 * Take the token offered by `GET /assistant/config/` only when none is held.
 * The config endpoint mints a fresh identity on every call; adopting it on
 * every page load would give the visitor a new identity (and budget) per
 * reload, so an existing one is kept.
 */
export function adoptVisitorToken(token: unknown): void {
  if (getVisitorToken() !== null) return;
  storeVisitorToken(token);
}

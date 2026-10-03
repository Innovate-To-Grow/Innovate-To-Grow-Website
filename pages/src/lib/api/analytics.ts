import { api } from './api-client';

interface PageViewPayload {
  path: string;
  referrer: string;
}

/**
 * A random id for this browser, sent with every page view as `visitor_id`.
 *
 * Most visitors share the campus public IP, so the backend cannot tell them apart by address: it throttles page
 * views and counts unique visitors by this id instead. It is random, carries no account or device information,
 * and is not a credential.
 */
export const VISITOR_ID_STORAGE_KEY = 'i2g_visitor_id';

// What the backend accepts (anything else is ignored there): a UUID or up to 64 URL-safe characters.
const VISITOR_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

// Only used while localStorage is unreadable or unwritable (private mode, blocked site data): one id per page load.
let memoryVisitorId: string | null = null;

function randomUuid(): string {
  const cryptoApi: Crypto | undefined = globalThis.crypto;
  // randomUUID only exists in secure contexts and recent browsers.
  if (typeof cryptoApi?.randomUUID === 'function') return cryptoApi.randomUUID();

  const bytes = new Uint8Array(16);
  if (typeof cryptoApi?.getRandomValues === 'function') {
    cryptoApi.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // RFC 4122 variant
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** The stored visitor id, creating and storing one on first use. Never throws. */
export function getVisitorId(): string {
  try {
    // Read storage on every call (no module cache) so tabs opened together settle on one id, and so clearing the
    // site data really starts a new one.
    const stored = window.localStorage.getItem(VISITOR_ID_STORAGE_KEY);
    if (stored && VISITOR_ID_PATTERN.test(stored)) return stored;

    const created = randomUuid();
    window.localStorage.setItem(VISITOR_ID_STORAGE_KEY, created);
    return created;
  } catch {
    memoryVisitorId ??= randomUuid();
    return memoryVisitorId;
  }
}

export const trackPageView = async (payload: PageViewPayload): Promise<void> => {
  try {
    // An older backend ignores the extra field, so this is safe to deploy in either order.
    await api.post('/analytics/pageview/', {...payload, visitor_id: getVisitorId()});
  } catch {
    // Silently fail — tracking should never break the user experience
  }
};

import {
  type AuthCallbackRoute,
  type CallbackMemoryWindow,
  readStoredParams,
  storageKey,
  storeHandoff,
} from './callbackHandoff';

export type {AuthCallbackRoute} from './callbackHandoff';

const CALLBACK_ROUTES: Readonly<
  Record<string, {route: AuthCallbackRoute; fields: readonly string[]}>
> = {
  '/login-link': {route: 'login-link', fields: ['token']},
  '/magic-login': {route: 'login-link', fields: ['token']},
  '/ticket-login': {route: 'login-link', fields: ['token']},
  '/impersonate-login': {route: 'impersonate-login', fields: ['token']},
  '/email-auth-link': {
    route: 'email-auth-link',
    fields: ['flow', 'source', 'email', 'code', 'event'],
  },
};

const readFragmentParams = () => {
  if (typeof window === 'undefined') return new URLSearchParams();
  let raw = window.location.hash.slice(1);
  if (raw.startsWith('?')) raw = raw.slice(1);
  return raw.includes('=') ? new URLSearchParams(raw) : new URLSearchParams();
};

/** Remove each field from the query and fragment, returning the values found. */
const takeFields = (
  fields: readonly string[],
  query: URLSearchParams,
  fragment: URLSearchParams,
): Record<string, string> => {
  const captured: Record<string, string> = {};
  for (const field of fields) {
    const value = query.get(field) ?? fragment.get(field);
    if (value !== null) captured[field] = value;
    query.delete(field);
    fragment.delete(field);
  }
  return captured;
};

const scrubbedUrl = (pathname: string, query: string, hash: string) =>
  pathname + (query ? `?${query}` : '') + (hash ? `#${hash}` : '');

/**
 * An SMS short link carries its token in the path (`/l/<token>`), not in the
 * query or the fragment: keep the token and show `/l` instead, so nothing that
 * reads the address later (analytics, the referrer of the next request) sees it.
 */
const SMS_LINK_PATH = /^\/l\/([A-Za-z0-9_-]{16,64})\/?$/;
export const SMS_LINK_ROUTE_PATH = '/l';

const captureSmsLinkToken = (): boolean => {
  const match = SMS_LINK_PATH.exec(window.location.pathname);
  if (!match) return false;
  storeHandoff('sms-link', {capturedAt: Date.now(), params: {token: match[1]}});
  window.history.replaceState(window.history.state, '', SMS_LINK_ROUTE_PATH);
  return true;
};

export const captureAuthCallbackParams = (): void => {
  if (typeof window === 'undefined') return;
  if (captureSmsLinkToken()) return;
  const config = CALLBACK_ROUTES[window.location.pathname];
  if (!config) return;

  const query = new URLSearchParams(window.location.search);
  let rawHash = window.location.hash.slice(1);
  if (rawHash.startsWith('?')) rawHash = rawHash.slice(1);
  const hashLooksLikeParams = rawHash.includes('=');
  const fragment = hashLooksLikeParams
    ? new URLSearchParams(rawHash)
    : new URLSearchParams();
  const captured = takeFields(config.fields, query, fragment);
  if (Object.keys(captured).length > 0) {
    storeHandoff(config.route, {capturedAt: Date.now(), params: captured});
  }

  const nextHash = hashLooksLikeParams ? fragment.toString() : rawHash;
  window.history.replaceState(
    window.history.state,
    '',
    scrubbedUrl(window.location.pathname, query.toString(), nextHash),
  );
};

export const readAuthCallbackParams = (
  route: AuthCallbackRoute,
  fallback: URLSearchParams,
): URLSearchParams => {
  const result = new URLSearchParams();
  const stored = readStoredParams(route);
  const fragment = readFragmentParams();
  const keys = new Set([
    ...Object.keys(stored),
    ...fallback.keys(),
    ...fragment.keys(),
  ]);
  keys.forEach((key) => {
    const value = stored[key] ?? fallback.get(key) ?? fragment.get(key);
    if (value !== null && value !== undefined) result.set(key, value);
  });
  return result;
};

export const clearAuthCallbackParams = (route: AuthCallbackRoute) => {
  try {
    sessionStorage.removeItem(storageKey(route));
  } catch {
    // The values are already held in component state and the URL was scrubbed.
  }
  const memoryWindow = window as CallbackMemoryWindow;
  if (memoryWindow.__i2gCallbackHandoff) {
    delete memoryWindow.__i2gCallbackHandoff[route];
    if (Object.keys(memoryWindow.__i2gCallbackHandoff).length === 0) {
      delete memoryWindow.__i2gCallbackHandoff;
    }
  }
};

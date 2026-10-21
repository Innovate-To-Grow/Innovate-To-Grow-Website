export type AuthCallbackRoute =
  | 'login-link'
  | 'impersonate-login'
  | 'email-auth-link';

const CALLBACK_STORAGE_PREFIX = 'i2g_callback_params:';
const CALLBACK_MAX_AGE_MS = 15 * 60 * 1000;

interface StoredCallbackParams {
  capturedAt: number;
  params: Record<string, string>;
}

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

type CallbackMemoryWindow = Window &
  typeof globalThis & {
    __i2gCallbackHandoff?: Partial<
      Record<AuthCallbackRoute, StoredCallbackParams>
    >;
  };

const storageKey = (route: AuthCallbackRoute) =>
  `${CALLBACK_STORAGE_PREFIX}${route}`;

const normalizeStoredParams = (
  parsed: Partial<StoredCallbackParams> | undefined,
): Record<string, string> => {
  if (
    !parsed ||
    typeof parsed.capturedAt !== 'number' ||
    Date.now() - parsed.capturedAt > CALLBACK_MAX_AGE_MS ||
    !parsed.params ||
    typeof parsed.params !== 'object'
  ) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(parsed.params).filter(
      (entry): entry is [string, string] =>
        typeof entry[1] === 'string',
    ),
  );
};

const readStoredParams = (
  route: AuthCallbackRoute,
): Record<string, string> => {
  try {
    const serialized = sessionStorage.getItem(storageKey(route));
    if (serialized) {
      const parsed = JSON.parse(serialized) as Partial<StoredCallbackParams>;
      const normalized = normalizeStoredParams(parsed);
      if (Object.keys(normalized).length > 0) return normalized;
      sessionStorage.removeItem(storageKey(route));
    }
  } catch {
    // Fall through to the memory handoff used when sessionStorage is denied.
  }

  const memoryWindow = window as CallbackMemoryWindow;
  return normalizeStoredParams(memoryWindow.__i2gCallbackHandoff?.[route]);
};

const readFragmentParams = () => {
  if (typeof window === 'undefined') return new URLSearchParams();
  let raw = window.location.hash.slice(1);
  if (raw.startsWith('?')) raw = raw.slice(1);
  return raw.includes('=') ? new URLSearchParams(raw) : new URLSearchParams();
};

/**
 * Keep the captured params for the route: in sessionStorage, or (when storage
 * is refused) on the window.
 */
const storeHandoff = (
  route: AuthCallbackRoute,
  handoff: StoredCallbackParams,
) => {
  try {
    sessionStorage.setItem(storageKey(route), JSON.stringify(handoff));
    return;
  } catch {
    // Storage refused (private mode, quota): fall back to window memory below.
  }
  const memoryWindow = window as CallbackMemoryWindow;
  const memory = memoryWindow.__i2gCallbackHandoff ?? {};
  memory[route] = handoff;
  try {
    Object.defineProperty(memoryWindow, '__i2gCallbackHandoff', {
      configurable: true,
      enumerable: false,
      value: memory,
      writable: true,
    });
  } catch {
    memoryWindow.__i2gCallbackHandoff = memory;
  }
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

export const captureAuthCallbackParams = (): void => {
  if (typeof window === 'undefined') return;
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

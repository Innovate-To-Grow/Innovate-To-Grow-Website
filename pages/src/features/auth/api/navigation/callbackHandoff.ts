export type AuthCallbackRoute =
  | 'login-link'
  | 'impersonate-login'
  | 'email-auth-link'
  | 'sms-link';

const CALLBACK_STORAGE_PREFIX = 'i2g_callback_params:';
const CALLBACK_MAX_AGE_MS = 15 * 60 * 1000;

interface StoredCallbackParams {
  capturedAt: number;
  params: Record<string, string>;
}

export type CallbackMemoryWindow = Window &
  typeof globalThis & {
    __i2gCallbackHandoff?: Partial<
      Record<AuthCallbackRoute, StoredCallbackParams>
    >;
  };

export const storageKey = (route: AuthCallbackRoute) =>
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

export const readStoredParams = (
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

/**
 * Keep the captured params for the route: in sessionStorage, or (when storage
 * is refused) on the window.
 */
export const storeHandoff = (
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

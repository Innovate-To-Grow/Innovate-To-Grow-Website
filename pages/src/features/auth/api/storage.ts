import type {AuthTokens, LoginResponse, User} from './types';

const AUTH_SESSION_KEY = 'i2g_auth_session';
const AUTH_SESSION_VERSION = 1;

// Legacy keys are read once and removed after migration. Keep these names stable
// until all previously issued browser sessions have had a chance to migrate.
const LEGACY_ACCESS_TOKEN_KEY = 'i2g_access_token';
const LEGACY_REFRESH_TOKEN_KEY = 'i2g_refresh_token';
const LEGACY_USER_KEY = 'i2g_user';
const LEGACY_PROFILE_COMPLETION_REQUIRED_KEY = 'i2g_profile_completion_required';

export interface StoredAuthSession {
  version: typeof AUTH_SESSION_VERSION;
  generation: string;
  access: string;
  refresh: string;
  user: User;
  requires_profile_completion: boolean;
}

export interface SessionGuard {
  generation: string;
  refresh?: string;
}

let fallbackGeneration = 0;

const createGeneration = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  fallbackGeneration += 1;
  return `${Date.now().toString(36)}-${fallbackGeneration.toString(36)}`;
};

const safeLocalGet = (key: string) => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

const safeLocalSet = (key: string, value: string) => {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
};

const safeLocalRemove = (key: string) => {
  try {
    localStorage.removeItem(key);
  } catch {
    // Storage can be denied in embedded/privacy-restricted contexts.
  }
};

const safeSessionGet = (key: string) => {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
};

const safeSessionRemove = (key: string) => {
  try {
    sessionStorage.removeItem(key);
  } catch {
    // Storage can be denied in embedded/privacy-restricted contexts.
  }
};

const removeLegacySession = () => {
  safeLocalRemove(LEGACY_ACCESS_TOKEN_KEY);
  safeLocalRemove(LEGACY_REFRESH_TOKEN_KEY);
  safeLocalRemove(LEGACY_USER_KEY);
  safeSessionRemove(LEGACY_PROFILE_COMPLETION_REQUIRED_KEY);
};

const isUser = (value: unknown): value is User => {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<User>;
  return (
    typeof candidate.member_uuid === 'string' &&
    typeof candidate.email === 'string'
  );
};

const isStoredAuthSession = (value: unknown): value is StoredAuthSession => {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<StoredAuthSession>;
  return (
    candidate.version === AUTH_SESSION_VERSION &&
    typeof candidate.generation === 'string' &&
    Boolean(candidate.generation) &&
    typeof candidate.access === 'string' &&
    typeof candidate.refresh === 'string' &&
    isUser(candidate.user) &&
    typeof candidate.requires_profile_completion === 'boolean'
  );
};

const writeSession = (session: StoredAuthSession) => {
  const stored = safeLocalSet(AUTH_SESSION_KEY, JSON.stringify(session));
  if (stored) removeLegacySession();
  return stored;
};

const requireSessionWrite = (session: StoredAuthSession) => {
  if (!writeSession(session)) {
    throw new Error('Unable to persist the authentication session.');
  }
  return session;
};

const readCurrentRecord = (): StoredAuthSession | null => {
  const serialized = safeLocalGet(AUTH_SESSION_KEY);
  if (!serialized) return null;
  try {
    const parsed: unknown = JSON.parse(serialized);
    if (isStoredAuthSession(parsed)) return parsed;
  } catch {
    // Invalid or obsolete records are removed below.
  }
  safeLocalRemove(AUTH_SESSION_KEY);
  return null;
};

const migrateLegacySession = (): StoredAuthSession | null => {
  const access = safeLocalGet(LEGACY_ACCESS_TOKEN_KEY);
  const refresh = safeLocalGet(LEGACY_REFRESH_TOKEN_KEY);
  const serializedUser = safeLocalGet(LEGACY_USER_KEY);

  if (!access || !refresh || !serializedUser) {
    removeLegacySession();
    return null;
  }

  try {
    const user: unknown = JSON.parse(serializedUser);
    if (!isUser(user)) {
      removeLegacySession();
      return null;
    }
    const migrated: StoredAuthSession = {
      version: AUTH_SESSION_VERSION,
      generation: createGeneration(),
      access,
      refresh,
      user,
      requires_profile_completion:
        safeSessionGet(LEGACY_PROFILE_COMPLETION_REQUIRED_KEY) === 'true',
    };
    if (!writeSession(migrated)) return null;
    return migrated;
  } catch {
    removeLegacySession();
    return null;
  }
};

export const getStoredSession = (): StoredAuthSession | null =>
  readCurrentRecord() ?? migrateLegacySession();

export const isCurrentSession = (guard: SessionGuard): boolean => {
  const current = getStoredSession();
  return Boolean(
    current &&
      current.generation === guard.generation &&
      (guard.refresh === undefined || current.refresh === guard.refresh),
  );
};

export const isProfileCompletionRequired = (): boolean =>
  getStoredSession()?.requires_profile_completion ?? false;

export const setProfileCompletionRequired = (required: boolean): boolean => {
  const current = getStoredSession();
  if (!current) return false;
  return writeSession({...current, requires_profile_completion: required});
};

export const clearProfileCompletionRequired = (guard?: SessionGuard): boolean => {
  const current = getStoredSession();
  if (
    !current ||
    (guard &&
      (current.generation !== guard.generation ||
        (guard.refresh !== undefined && current.refresh !== guard.refresh)))
  ) {
    return false;
  }
  if (!writeSession({...current, requires_profile_completion: false})) {
    return false;
  }
  safeSessionRemove(LEGACY_PROFILE_COMPLETION_REQUIRED_KEY);
  return true;
};

export const getAccessToken = (): string | null =>
  getStoredSession()?.access ?? null;

export const getRefreshToken = (): string | null =>
  getStoredSession()?.refresh ?? null;

export const getStoredUser = (): User | null =>
  getStoredSession()?.user ?? null;

export const setTokens = (tokens: AuthTokens, user: User): StoredAuthSession => {
  const session: StoredAuthSession = {
    version: AUTH_SESSION_VERSION,
    generation: createGeneration(),
    access: tokens.access,
    refresh: tokens.refresh,
    user,
    requires_profile_completion: false,
  };
  return requireSessionWrite(session);
};

export const persistAuthSession = (
  response: Pick<
    LoginResponse,
    'access' | 'refresh' | 'user' | 'requires_profile_completion'
  >,
): StoredAuthSession => {
  const session: StoredAuthSession = {
    version: AUTH_SESSION_VERSION,
    generation: createGeneration(),
    access: response.access,
    refresh: response.refresh,
    user: response.user,
    requires_profile_completion: Boolean(
      response.requires_profile_completion,
    ),
  };
  return requireSessionWrite(session);
};

export const updateSessionTokens = (
  guard: SessionGuard,
  tokens: AuthTokens,
): StoredAuthSession | null => {
  const current = getStoredSession();
  if (
    !current ||
    current.generation !== guard.generation ||
    (guard.refresh !== undefined && current.refresh !== guard.refresh)
  ) {
    return null;
  }
  const updated = {...current, access: tokens.access, refresh: tokens.refresh};
  return writeSession(updated) ? updated : null;
};

export const updateStoredUser = (
  updater: (user: User) => User,
  expectedGeneration?: string,
): User | null => {
  const current = getStoredSession();
  if (
    !current ||
    (expectedGeneration !== undefined &&
      current.generation !== expectedGeneration)
  ) {
    return null;
  }
  const user = updater(current.user);
  return writeSession({...current, user}) ? user : null;
};

export const updateStoredSessionProfile = (
  guard: SessionGuard,
  user: User,
  requiresProfileCompletion: boolean,
): StoredAuthSession | null => {
  const current = getStoredSession();
  if (
    !current ||
    current.generation !== guard.generation ||
    (guard.refresh !== undefined && current.refresh !== guard.refresh)
  ) {
    return null;
  }
  const updated = {
    ...current,
    user,
    requires_profile_completion: requiresProfileCompletion,
  };
  return writeSession(updated) ? updated : null;
};

export const clearTokens = (guard?: SessionGuard): boolean => {
  const current = getStoredSession();
  if (
    guard &&
    (!current ||
      current.generation !== guard.generation ||
      (guard.refresh !== undefined && current.refresh !== guard.refresh))
  ) {
    return false;
  }
  safeLocalRemove(AUTH_SESSION_KEY);
  removeLegacySession();
  return true;
};

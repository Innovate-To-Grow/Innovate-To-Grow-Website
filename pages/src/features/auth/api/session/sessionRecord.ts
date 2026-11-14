import {SessionNotSavedError} from '../contracts/errors';
import type {User} from '../contracts/types';

export const AUTH_SESSION_KEY = 'i2g_auth_session';
export const AUTH_SESSION_VERSION = 1;

// Legacy keys are read once and removed after migration. Keep these names stable
// until all previously issued browser sessions have had a chance to migrate.
const LEGACY_ACCESS_TOKEN_KEY = 'i2g_access_token';
const LEGACY_REFRESH_TOKEN_KEY = 'i2g_refresh_token';
const LEGACY_USER_KEY = 'i2g_user';
export const LEGACY_PROFILE_COMPLETION_REQUIRED_KEY = 'i2g_profile_completion_required';

export interface StoredAuthSession {
  version: typeof AUTH_SESSION_VERSION;
  generation: string;
  access: string;
  refresh: string;
  user: User;
  requires_profile_completion: boolean;
}

let fallbackGeneration = 0;

export const createGeneration = () => {
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

export const safeLocalRemove = (key: string) => {
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

export const safeSessionRemove = (key: string) => {
  try {
    sessionStorage.removeItem(key);
  } catch {
    // Storage can be denied in embedded/privacy-restricted contexts.
  }
};

export const removeLegacySession = () => {
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

// The API uses null for an absent image, while older sessions omit the field.
// Store one representation so profile/session responses cannot alternate the
// record and trigger an endless chain of cross-tab storage events.
export const normalizeStoredUser = (user: User): User => {
  const {profile_image, ...rest} = user;
  return typeof profile_image === 'string' && profile_image
    ? {...rest, profile_image}
    : rest;
};

export const writeSession = (session: StoredAuthSession) => {
  const serialized = JSON.stringify({...session, user: normalizeStoredUser(session.user)});
  const stored = safeLocalGet(AUTH_SESSION_KEY) === serialized ||
    safeLocalSet(AUTH_SESSION_KEY, serialized);
  if (stored) removeLegacySession();
  return stored;
};

export const requireSessionWrite = (session: StoredAuthSession) => {
  if (!writeSession(session)) {
    throw new SessionNotSavedError();
  }
  return session;
};

export const readCurrentRecord = (): StoredAuthSession | null => {
  const serialized = safeLocalGet(AUTH_SESSION_KEY);
  if (!serialized) return null;
  try {
    const parsed: unknown = JSON.parse(serialized);
    if (isStoredAuthSession(parsed)) return {...parsed, user: normalizeStoredUser(parsed.user)};
  } catch {
    // Invalid or obsolete records are removed below.
  }
  safeLocalRemove(AUTH_SESSION_KEY);
  return null;
};

export const migrateLegacySession = (): StoredAuthSession | null => {
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
      user: normalizeStoredUser(user),
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

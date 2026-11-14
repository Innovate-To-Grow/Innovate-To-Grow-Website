import type {AuthTokens, LoginResponse, User} from '../contracts/types';
import {
  AUTH_SESSION_KEY,
  AUTH_SESSION_VERSION,
  createGeneration,
  LEGACY_PROFILE_COMPLETION_REQUIRED_KEY,
  migrateLegacySession,
  normalizeStoredUser,
  readCurrentRecord,
  removeLegacySession,
  requireSessionWrite,
  safeLocalRemove,
  safeSessionRemove,
  type StoredAuthSession,
  writeSession,
} from './sessionRecord';

export {AUTH_SESSION_KEY} from './sessionRecord';
export type {StoredAuthSession} from './sessionRecord';

export interface SessionGuard {
  generation: string;
  refresh?: string;
}

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
    user: normalizeStoredUser(user),
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
    user: normalizeStoredUser(response.user),
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
  const user = normalizeStoredUser(updater(current.user));
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
    user: normalizeStoredUser(user),
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

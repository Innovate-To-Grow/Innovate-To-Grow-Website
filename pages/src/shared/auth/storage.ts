import type { AuthTokens, User } from './types';

const ACCESS_TOKEN_KEY = 'i2g_access_token';
const REFRESH_TOKEN_KEY = 'i2g_refresh_token';
const USER_KEY = 'i2g_user';
const PROFILE_COMPLETION_REQUIRED_KEY = 'i2g_profile_completion_required';

export const isProfileCompletionRequired = (): boolean => {
  return sessionStorage.getItem(PROFILE_COMPLETION_REQUIRED_KEY) === 'true';
};

export const setProfileCompletionRequired = (required: boolean): void => {
  if (required) {
    sessionStorage.setItem(PROFILE_COMPLETION_REQUIRED_KEY, 'true');
    return;
  }
  sessionStorage.removeItem(PROFILE_COMPLETION_REQUIRED_KEY);
};

export const clearProfileCompletionRequired = (): void => {
  sessionStorage.removeItem(PROFILE_COMPLETION_REQUIRED_KEY);
};

export const getAccessToken = (): string | null => {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
};

export const getRefreshToken = (): string | null => {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
};

export const getStoredUser = (): User | null => {
  const userStr = localStorage.getItem(USER_KEY);
  if (!userStr) return null;
  try {
    return JSON.parse(userStr);
  } catch {
    return null;
  }
};

export const setTokens = (tokens: AuthTokens, user: User): void => {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
};

export const updateStoredUser = (updater: (user: User) => User): void => {
  const user = getStoredUser();
  if (!user) return;
  localStorage.setItem(USER_KEY, JSON.stringify(updater(user)));
};

export const clearTokens = (): void => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  clearProfileCompletionRequired();
};

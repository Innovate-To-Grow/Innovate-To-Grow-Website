import { authApi } from './client';
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  persistAuthSession,
} from './storage';
import type { LoginResponse, UnsubscribeResponse } from './types';

export const loginLinkAutoLogin = async (token: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/mail/login-link/', { token });
  persistAuthSession(response.data);
  return response.data;
};

export const unsubscribeAutoLogin = async (token: string): Promise<UnsubscribeResponse> => {
  const response = await authApi.post<UnsubscribeResponse>('/authn/unsubscribe-login/', { token });
  return response.data;
};

export const impersonateAutoLogin = async (token: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/authn/impersonate-login/', { token });
  persistAuthSession(response.data);
  return response.data;
};

export const logout = async (): Promise<void> => {
  // Clear local state first so any listener that responds to the auth-state
  // change event reads empty storage, and so the user is effectively logged
  // out even if the server call hangs or fails. The server-side blacklist is
  // best-effort and fires in the background — callers that await logout()
  // still return promptly.
  const refresh = getRefreshToken();
  clearTokens();
  window.dispatchEvent(new Event('i2g-auth-state-change'));
  if (refresh) {
    void authApi.post('/authn/logout/', { refresh }).catch(() => {
      /* noop — local logout already complete */
    });
  }
};

export const isAuthenticated = (): boolean => {
  const token = getAccessToken();
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return typeof payload.exp === 'number' && payload.exp > Date.now() / 1000;
  } catch {
    return false;
  }
};

import authApi from './client';
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  persistAuthSession,
} from './storage';
import type { LoginResponse } from './types';

export const ticketAutoLogin = async (token: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/event/ticket-login/', { token });
  persistAuthSession(response.data);
  return response.data;
};

export const magicAutoLogin = async (token: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/mail/magic-login/', { token });
  persistAuthSession(response.data);
  return response.data;
};

export const unsubscribeAutoLogin = async (token: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/authn/unsubscribe-login/', { token });
  persistAuthSession(response.data);
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

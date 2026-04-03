import authApi from './client';
import { clearProfileCompletionRequired, clearTokens, getAccessToken, setTokens } from './storage';
import type { LoginResponse } from './types';

export const ticketAutoLogin = async (token: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/event/ticket-login/', { token });
  const { access, refresh, user } = response.data;
  setTokens({ access, refresh }, user);
  clearProfileCompletionRequired();
  return response.data;
};

export const magicAutoLogin = async (token: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/mail/magic-login/', { token });
  const { access, refresh, user } = response.data;
  setTokens({ access, refresh }, user);
  clearProfileCompletionRequired();
  return response.data;
};

export const unsubscribeAutoLogin = async (token: string): Promise<LoginResponse> => {
  const response = await authApi.post<LoginResponse>('/authn/unsubscribe-login/', { token });
  const { access, refresh, user } = response.data;
  setTokens({ access, refresh }, user);
  clearProfileCompletionRequired();
  return response.data;
};

export const logout = (): void => {
  clearTokens();
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

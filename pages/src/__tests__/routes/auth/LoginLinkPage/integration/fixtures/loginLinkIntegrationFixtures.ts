import axios, {
  AxiosError,
  type AxiosAdapter,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';

import {authApi} from '@/features/auth/api/session/client';
import {captureAuthCallbackParams} from '@/features/auth/api/navigation/callbackParams';
import {persistAuthSession} from '@/features/auth/api/session/storage';

export const EMAILED_TOKEN = 'emailed-token';
export const STALE_ACCESS = 'stale-access';

// Someone else's account, for a browser that signs in by code instead of by link.
export const MEMBER_B = {member_uuid: 'member-b', email: 'b@example.com'};

export const NEW_ACCOUNT = {
  message: 'Login successful.',
  access: 'new-access',
  refresh: 'new-refresh',
  user: {member_uuid: 'member-new', email: 'new@example.com'},
  requires_profile_completion: false,
  redirect_to: '/schedule',
};

export interface RecordedRequest {
  url: string;
  authorization: unknown;
  body: unknown;
}

export type Reply = {status: number; data: unknown};

export const reply = (config: InternalAxiosRequestConfig, {status, data}: Reply) => {
  const response = {
    data,
    status,
    statusText: '',
    headers: {},
    config,
    request: {},
  } as AxiosResponse;
  if (status >= 200 && status < 300) return Promise.resolve(response);
  return Promise.reject(
    new AxiosError(
      `Request failed with status code ${status}`,
      status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
      config,
      {},
      response,
    ),
  );
};

export const seedStaleSession = () =>
  persistAuthSession({
    access: STALE_ACCESS,
    refresh: 'stale-refresh',
    user: {member_uuid: 'member-old', email: 'old@example.com'},
    requires_profile_completion: false,
  });

// What main.tsx does before React mounts: the token moves into the
// sessionStorage handoff and the URL is scrubbed.
export const seedHandoff = (token: string) => {
  window.history.replaceState(null, '', `/login-link#token=${token}`);
  sessionStorage.clear();
  captureAuthCallbackParams();
};

export const useAdapter = (adapter: AxiosAdapter) => {
  // authApi carries its own copy of the defaults, and the refresh call goes
  // through the global instance, so both need the fake.
  authApi.defaults.adapter = adapter;
  axios.defaults.adapter = adapter;
};

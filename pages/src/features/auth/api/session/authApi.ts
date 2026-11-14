import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

declare module 'axios' {
  // The type parameter must match axios' own declaration to merge.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unused-vars
  interface AxiosRequestConfig<D = any> {
    /**
     * Opt out of the stored member session for this request. Set it on
     * endpoints that authenticate by a one-time credential in the request body
     * (emailed login links, impersonation tokens): no Authorization
     * header is sent, and a failure never refreshes, retries, or clears the
     * stored session — an anonymous exchange must neither use nor destroy it.
     */
    skipAuth?: boolean;
    /** Refresh an expired stored token before a public request that reads the member. */
    requireFreshIdentity?: boolean;
  }
}

export const authApi = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface RequestSession {
  generation: string;
  access: string;
}

export const requestSessions = new WeakMap<object, RequestSession>();

import {type InternalAxiosRequestConfig} from 'axios';

// Deep import, not the @/lib/api barrel: the barrel creates the shared client, which this module does not use.
import {handleRateLimitError} from '@/lib/api/rateLimit';

import {getStoredSession} from './storage';
import {authApi, requestSessions} from './authApi';
import {accessNeedsRefresh, refreshAccessTokenAttempt} from './tokenRefresh';
import {retryUnauthorized} from './unauthorizedRetry';

// Re-exported so callers (and test mocks) keep one module for the auth client.
export {API_BASE_URL} from './authApi';
export {refreshAccessToken} from './tokenRefresh';
export {isDefinitiveAuthFailure} from './unauthorizedRetry';

/**
 * Remove every spelling of the Authorization header. Header names are
 * case-insensitive on the wire, so a caller-supplied `authorization` must not
 * survive an opt-out. `AxiosHeaders` deletes case-insensitively on its own; a
 * plain object (older call sites, tests) needs each casing found by hand.
 */
const stripAuthorizationHeader = (
  headers: InternalAxiosRequestConfig['headers'] | undefined,
) => {
  if (!headers) return;
  if (typeof headers.delete === 'function') {
    headers.delete('Authorization');
    return;
  }
  const plain = headers as unknown as Record<string, unknown>;
  for (const name of Object.keys(plain)) {
    if (name.toLowerCase() === 'authorization') delete plain[name];
  }
};

const attachStoredSession = (config: InternalAxiosRequestConfig) => {
  const session = getStoredSession();
  if (session) {
    config.headers.Authorization = `Bearer ${session.access}`;
    requestSessions.set(config, {
      generation: session.generation,
      access: session.access,
    });
  } else if (config.headers) {
    stripAuthorizationHeader(config.headers);
  }
  return config;
};

authApi.interceptors.request.use((config) => {
  if (config.data instanceof FormData && config.headers) {
    delete config.headers['Content-Type'];
  }
  if (config.skipAuth) {
    // The stored session is neither read nor recorded for this request.
    stripAuthorizationHeader(config.headers);
    return config;
  }
  const snapshot = getStoredSession();
  if (config.requireFreshIdentity && snapshot && accessNeedsRefresh(snapshot.access)) {
    return refreshAccessTokenAttempt(snapshot.generation).then(() => {
      const current = getStoredSession();
      if (current && current.generation !== snapshot.generation) {
        throw new Error('The member session changed while this request was waiting.');
      }
      if (current && current.access === snapshot.access) {
        // A transient refresh failure must not make a member-aware public view
        // look anonymous while the same stored session is still present.
        throw new Error('The member session could not be refreshed.');
      }
      return attachStoredSession(config);
    });
  }
  return attachStoredSession(config);
});

authApi.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Anonymous exchange: a stale stored session must be neither refreshed nor
    // cleared on its behalf (nor retried: these are one-time credentials in a POST).
    if (originalRequest?.skipAuth) return Promise.reject(error);

    if (error.response?.status === 401 && originalRequest) {
      return retryUnauthorized(error, originalRequest);
    }
    // A 429 on a read waits out Retry-After and retries once (lib/api/rateLimit); the session is never touched.
    if (error.response?.status === 429) return handleRateLimitError(authApi, error);
    return Promise.reject(error);
  },
);

export {authApi};

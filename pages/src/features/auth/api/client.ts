import axios, {type InternalAxiosRequestConfig} from 'axios';

import {
  clearTokens,
  getStoredSession,
  updateSessionTokens,
  type SessionGuard,
} from './storage';

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
  }
}

const authApi = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

interface RequestSession {
  generation: string;
  access: string;
}

type RefreshResult = RequestSession;

type RefreshFailure =
  | 'definitive'
  | 'transient'
  | 'session_changed';

interface RefreshAttempt {
  result: RefreshResult | null;
  failure?: RefreshFailure;
}

interface RefreshInFlight {
  key: string;
  promise: Promise<RefreshAttempt>;
}

let refreshInFlight: RefreshInFlight | null = null;
const requestSessions = new WeakMap<object, RequestSession>();
const AUTH_RETRY_MARKER = '_i2gAuthRetried';
const AUTH_FAILURE_MARKER = '_i2gAuthFailure';

type AuthFailure = {
  [AUTH_FAILURE_MARKER]?: 'definitive';
};

const responseStatus = (error: unknown): number | undefined => {
  if (!error || typeof error !== 'object') return undefined;
  const response = (error as {response?: unknown}).response;
  if (!response || typeof response !== 'object') return undefined;
  const status = (response as {status?: unknown}).status;
  return typeof status === 'number' ? status : undefined;
};

const markDefinitiveAuthFailure = (error: unknown) => {
  if (error && typeof error === 'object') {
    (error as AuthFailure)[AUTH_FAILURE_MARKER] = 'definitive';
  }
};

export const isDefinitiveAuthFailure = (error: unknown): boolean =>
  Boolean(
    error &&
      typeof error === 'object' &&
      (error as AuthFailure)[AUTH_FAILURE_MARKER] === 'definitive',
  );

const dispatchAuthStateChange = () => {
  window.dispatchEvent(new Event('i2g-auth-state-change'));
};

/**
 * Refresh the current generation only. If another tab logs out or replaces the
 * account while the request is in flight, the response is discarded.
 */
async function refreshAccessTokenAttempt(
  expectedGeneration?: string,
): Promise<RefreshAttempt> {
  const snapshot = getStoredSession();
  if (
    !snapshot ||
    (expectedGeneration !== undefined &&
      snapshot.generation !== expectedGeneration)
  ) {
    return {result: null, failure: 'session_changed'};
  }

  const guard: SessionGuard = {
    generation: snapshot.generation,
    refresh: snapshot.refresh,
  };
  const key = `${guard.generation}:${guard.refresh}`;
  if (refreshInFlight?.key === key) return refreshInFlight.promise;

  const promise: Promise<RefreshAttempt> = axios
    .post(`${API_BASE_URL}/authn/refresh/`, {
      refresh: snapshot.refresh,
    })
    .then((response) => {
      const access = response.data?.access;
      if (typeof access !== 'string' || !access) {
        // A malformed success response is not proof that the refresh
        // credential is invalid. Keep the guarded session so a transient
        // deploy/proxy fault cannot log out the user.
        return {result: null, failure: 'transient'} as RefreshAttempt;
      }

      const refresh =
        typeof response.data?.refresh === 'string' && response.data.refresh
          ? response.data.refresh
          : snapshot.refresh;
      const updated = updateSessionTokens(guard, {access, refresh});
      if (!updated) {
        return {
          result: null,
          failure: 'session_changed',
        } as RefreshAttempt;
      }

      dispatchAuthStateChange();
      return {
        result: {access: updated.access, generation: updated.generation},
      } as RefreshAttempt;
    })
    .catch((error: unknown) => {
      const status = responseStatus(error);
      if (status === 400 || status === 401) {
        if (clearTokens(guard)) {
          dispatchAuthStateChange();
          return {
            result: null,
            failure: 'definitive',
          } as RefreshAttempt;
        }
        return {
          result: null,
          failure: 'session_changed',
        } as RefreshAttempt;
      }
      return {result: null, failure: 'transient'} as RefreshAttempt;
    })
    .finally(() => {
      if (refreshInFlight?.key === key) refreshInFlight = null;
    });

  refreshInFlight = {key, promise};
  return promise;
}

export async function refreshAccessToken(
  expectedGeneration?: string,
): Promise<RefreshResult | null> {
  return (await refreshAccessTokenAttempt(expectedGeneration)).result;
}

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

authApi.interceptors.request.use((config) => {
  if (config.skipAuth) {
    // The stored session is neither read nor recorded for this request.
    stripAuthorizationHeader(config.headers);
  } else {
    const session = getStoredSession();
    if (session) {
      config.headers.Authorization = `Bearer ${session.access}`;
      requestSessions.set(config, {
        generation: session.generation,
        access: session.access,
      });
    } else if (config.headers) {
      delete config.headers.Authorization;
    }
  }
  if (config.data instanceof FormData && config.headers) {
    delete config.headers['Content-Type'];
  }
  return config;
});

authApi.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Anonymous exchange: a stale stored session must be neither refreshed nor
    // cleared on its behalf.
    if (originalRequest?.skipAuth) return Promise.reject(error);

    if (error.response?.status === 401 && originalRequest) {
      const requestSession = requestSessions.get(originalRequest);
      const current = getStoredSession();
      const alreadyRetried = Boolean(originalRequest[AUTH_RETRY_MARKER]);

      if (alreadyRetried) {
        // A fresh token was still rejected. Clear only the exact generation
        // and access token used for that retry; a parallel refresh, login, or
        // account switch must survive this stale response.
        if (
          requestSession &&
          current &&
          current.generation === requestSession.generation &&
          current.access === requestSession.access &&
          clearTokens({
            generation: current.generation,
            refresh: current.refresh,
          })
        ) {
          dispatchAuthStateChange();
          markDefinitiveAuthFailure(error);
        }
        return Promise.reject(error);
      }

      // Never retry a request under another account, or turn a request that was
      // originally anonymous into an authenticated one.
      if (
        !requestSession ||
        !current ||
        current.generation !== requestSession.generation
      ) {
        return Promise.reject(error);
      }

      // Axios preserves unknown config fields when it merges a retry config, so
      // this marker follows the request and prevents a second refresh loop.
      originalRequest[AUTH_RETRY_MARKER] = true;

      // A parallel request may already have refreshed this generation.
      if (current.access !== requestSession.access) {
        originalRequest.headers.Authorization = `Bearer ${current.access}`;
        return authApi(originalRequest);
      }

      const attempt = await refreshAccessTokenAttempt(
        requestSession.generation,
      );
      if (attempt.result?.generation === requestSession.generation) {
        originalRequest.headers.Authorization =
          `Bearer ${attempt.result.access}`;
        return authApi(originalRequest);
      }

      // Another tab may have rotated this generation's tokens while our
      // refresh was in flight. Reuse that newer token; never clear or retry
      // under a different account generation.
      const latest = getStoredSession();
      if (
        latest &&
        latest.generation === requestSession.generation &&
        latest.access !== requestSession.access
      ) {
        originalRequest.headers.Authorization = `Bearer ${latest.access}`;
        return authApi(originalRequest);
      }

      if (attempt.failure === 'definitive') {
        markDefinitiveAuthFailure(error);
      }
    }

    return Promise.reject(error);
  },
);

export {authApi};

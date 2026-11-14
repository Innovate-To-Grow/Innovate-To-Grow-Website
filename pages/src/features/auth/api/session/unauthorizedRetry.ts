import {type InternalAxiosRequestConfig} from 'axios';

import {clearTokens, getStoredSession} from './storage';
import {authApi, type RequestSession, requestSessions} from './authApi';
import {dispatchAuthStateChange, refreshAccessTokenAttempt} from './tokenRefresh';

const AUTH_RETRY_MARKER = '_i2gAuthRetried';
const AUTH_FAILURE_MARKER = '_i2gAuthFailure';

type AuthFailure = {
  [AUTH_FAILURE_MARKER]?: 'definitive';
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

type RetriableRequest = InternalAxiosRequestConfig & {[AUTH_RETRY_MARKER]?: boolean};
type StoredSession = NonNullable<ReturnType<typeof getStoredSession>>;

const retryWithAccess = (request: RetriableRequest, access: string) => {
  request.headers.Authorization = `Bearer ${access}`;
  return authApi(request);
};

/**
 * A fresh token was still rejected. Clear only the exact generation and access token used for that
 * retry; a parallel refresh, login, or account switch must survive this stale response.
 */
const clearRejectedSession = (
  error: unknown,
  requestSession: RequestSession | undefined,
  current: StoredSession | null,
) => {
  if (
    requestSession &&
    current &&
    current.generation === requestSession.generation &&
    current.access === requestSession.access &&
    clearTokens({generation: current.generation, refresh: current.refresh})
  ) {
    dispatchAuthStateChange();
    markDefinitiveAuthFailure(error);
  }
};

const refreshAndRetry = async (error: unknown, request: RetriableRequest, requestSession: RequestSession) => {
  const attempt = await refreshAccessTokenAttempt(requestSession.generation);
  if (attempt.result?.generation === requestSession.generation) {
    return retryWithAccess(request, attempt.result.access);
  }

  // Another tab may have rotated this generation's tokens while our
  // refresh was in flight. Reuse that newer token; never clear or retry
  // under a different account generation.
  const latest = getStoredSession();
  if (latest && latest.generation === requestSession.generation && latest.access !== requestSession.access) {
    return retryWithAccess(request, latest.access);
  }

  if (attempt.failure === 'definitive') {
    markDefinitiveAuthFailure(error);
  }
  return Promise.reject(error);
};

/** A 401: retry once with a refreshed (or a parallel request's newer) token of the same session. */
export const retryUnauthorized = async (error: unknown, request: RetriableRequest) => {
  const requestSession = requestSessions.get(request);
  const current = getStoredSession();

  if (request[AUTH_RETRY_MARKER]) {
    clearRejectedSession(error, requestSession, current);
    return Promise.reject(error);
  }

  // Never retry a request under another account, or turn a request that was
  // originally anonymous into an authenticated one.
  if (!requestSession || !current || current.generation !== requestSession.generation) {
    return Promise.reject(error);
  }

  // Axios preserves unknown config fields when it merges a retry config, so
  // this marker follows the request and prevents a second refresh loop.
  request[AUTH_RETRY_MARKER] = true;

  // A parallel request may already have refreshed this generation.
  if (current.access !== requestSession.access) {
    return retryWithAccess(request, current.access);
  }
  return refreshAndRetry(error, request, requestSession);
};

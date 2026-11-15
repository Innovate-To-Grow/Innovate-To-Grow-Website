import axios from 'axios';

// Deep import, not the @/lib/api barrel: the barrel creates the shared client, which this module does not use.
import {rateLimitRetryDelay, waitUnlessAborted} from '@/lib/api/rateLimit';

import {
  clearTokens,
  getStoredSession,
  updateSessionTokens,
  type SessionGuard,
} from './storage';
import {API_BASE_URL, type RequestSession} from './authApi';

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

const responseStatus = (error: unknown): number | undefined => {
  if (!error || typeof error !== 'object') return undefined;
  const response = (error as {response?: unknown}).response;
  if (!response || typeof response !== 'object') return undefined;
  const status = (response as {status?: unknown}).status;
  return typeof status === 'number' ? status : undefined;
};

export const dispatchAuthStateChange = () => {
  window.dispatchEvent(new Event('i2g-auth-state-change'));
};

/**
 * Store the refreshed tokens for the guarded generation, keeping its refresh
 * token when none came back.
 */
function storeRefreshedTokens(
  data: {access?: unknown; refresh?: unknown} | undefined,
  guard: SessionGuard,
  currentRefresh: string,
): RefreshAttempt {
  const access = data?.access;
  if (typeof access !== 'string' || !access) {
    // A malformed success response is not proof that the refresh
    // credential is invalid. Keep the guarded session so a transient
    // deploy/proxy fault cannot log out the user.
    return {result: null, failure: 'transient'};
  }
  const refresh =
    typeof data?.refresh === 'string' && data.refresh
      ? data.refresh
      : currentRefresh;
  const updated = updateSessionTokens(guard, {access, refresh});
  if (!updated) return {result: null, failure: 'session_changed'};
  dispatchAuthStateChange();
  return {result: {access: updated.access, generation: updated.generation}};
}

/**
 * A rejected refresh (400/401) ends the guarded session; anything else is
 * transient.
 */
function refreshFailure(error: unknown, guard: SessionGuard): RefreshAttempt {
  const status = responseStatus(error);
  if (status !== 400 && status !== 401) {
    return {result: null, failure: 'transient'};
  }
  if (clearTokens(guard)) {
    dispatchAuthStateChange();
    return {result: null, failure: 'definitive'};
  }
  return {result: null, failure: 'session_changed'};
}

const sendRefresh = (refresh: string) => axios.post(`${API_BASE_URL}/authn/refresh/`, {refresh});

/**
 * POST the refresh token, once more after a 429 that asks for a short wait. A 429 is answered before the view runs,
 * so the token was neither used nor rotated and resending it is safe. A 429 that remains is transient
 * (`refreshFailure`): it never logs the member out.
 */
const postRefresh = (refresh: string) =>
  sendRefresh(refresh).catch(async (error: unknown) => {
    const delay = rateLimitRetryDelay(error);
    if (delay === null) throw error;
    await waitUnlessAborted(delay);
    return sendRefresh(refresh);
  });

/**
 * Refresh the current generation only. If another tab logs out or replaces the
 * account while the request is in flight, the response is discarded.
 */
export async function refreshAccessTokenAttempt(
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

  const promise: Promise<RefreshAttempt> = postRefresh(snapshot.refresh)
    .then((response) =>
      storeRefreshedTokens(response.data, guard, snapshot.refresh),
    )
    .catch((error: unknown) => refreshFailure(error, guard))
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

export const accessNeedsRefresh = (access: string): boolean => {
  try {
    const encoded = access.split('.')[1];
    if (!encoded) return true;
    const normalized = encoded.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(
      normalized.length + ((4 - (normalized.length % 4)) % 4),
      '=',
    );
    const payload = JSON.parse(atob(padded)) as {exp?: unknown};
    // Leave room for transit time and small client/server clock differences.
    return typeof payload.exp !== 'number' || payload.exp <= Date.now() / 1000 + 30;
  } catch {
    return true;
  }
};

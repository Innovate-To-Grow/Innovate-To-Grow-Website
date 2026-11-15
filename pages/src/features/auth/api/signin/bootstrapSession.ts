import {authApi, isDefinitiveAuthFailure} from '../session/client';
import {
  clearTokens,
  getStoredSession,
  updateStoredSessionProfile,
  type StoredAuthSession,
} from '../session/storage';
import {normalizeSessionUser, type SessionPayload} from './sessionPayload';

interface BootstrapInFlight {
  generation: string;
  promise: Promise<BootstrapAuthResult>;
}

export type BootstrapAuthResult =
  | {status: 'verified'; session: StoredAuthSession}
  | {status: 'anonymous'; session: null}
  | {status: 'unverified'; session: StoredAuthSession};

let bootstrapInFlight: BootstrapInFlight | null = null;

const dispatchAuthStateChange = () => {
  window.dispatchEvent(new Event('i2g-auth-state-change'));
};

const ANONYMOUS: BootstrapAuthResult = {status: 'anonymous', session: null};

/**
 * When the stored session is no longer the one being verified, report it as
 * it is (or anonymous).
 */
const supersededResult = (
  current: StoredAuthSession | null,
  snapshot: StoredAuthSession,
): BootstrapAuthResult | null => {
  if (current && current.generation === snapshot.generation) return null;
  return current ? {status: 'unverified', session: current} : ANONYMOUS;
};

const applySessionPayload = (
  current: StoredAuthSession,
  data: SessionPayload,
): BootstrapAuthResult => {
  if (data.authenticated === false) {
    if (
      clearTokens({generation: current.generation, refresh: current.refresh})
    ) {
      dispatchAuthStateChange();
    }
    return ANONYMOUS;
  }
  const normalized = normalizeSessionUser(
    data,
    current.user,
    current.requires_profile_completion,
  );
  if (!normalized) return {status: 'verified', session: current};
  const session = updateStoredSessionProfile(
    {generation: current.generation, refresh: current.refresh},
    normalized.user,
    normalized.requiresProfileCompletion,
  );
  return session ? {status: 'verified', session} : ANONYMOUS;
};

const bootstrapFailureResult = (
  current: StoredAuthSession,
  error: unknown,
): BootstrapAuthResult => {
  if (
    isDefinitiveAuthFailure(error) &&
    clearTokens({generation: current.generation, refresh: current.refresh})
  ) {
    dispatchAuthStateChange();
    return ANONYMOUS;
  }
  // A transient failure preserves display identity, but never establishes
  // authoritative authentication for protected client behavior.
  return {status: 'unverified', session: current};
};

/**
 * Verify the locally persisted generation against the backend and replace its
 * user/profile flags with the authoritative session payload. The auth client
 * refreshes an expired access token before retrying this request.
 */
export const bootstrapAuthSession =
  async (): Promise<BootstrapAuthResult> => {
    const snapshot = getStoredSession();
    if (!snapshot) return {status: 'anonymous', session: null};
    if (bootstrapInFlight?.generation === snapshot.generation) {
      return bootstrapInFlight.promise;
    }

    const promise: Promise<BootstrapAuthResult> = authApi
      .get<SessionPayload>('/authn/session/')
      .then<BootstrapAuthResult>((response) => {
        const current = getStoredSession();
        return (
          supersededResult(current, snapshot) ??
          applySessionPayload(current as StoredAuthSession, response.data)
        );
      })
      .catch((error: unknown): BootstrapAuthResult => {
        const current = getStoredSession();
        return (
          supersededResult(current, snapshot) ??
          bootstrapFailureResult(current as StoredAuthSession, error)
        );
      })
      .finally(() => {
        if (bootstrapInFlight?.generation === snapshot.generation) {
          bootstrapInFlight = null;
        }
      });

    bootstrapInFlight = {generation: snapshot.generation, promise};
    return promise;
  };

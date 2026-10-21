import {useEffect} from 'react';
import {bootstrapAuthSession, getStoredSession, type StoredAuthSession} from '@/features/auth/api';
import type {BootstrapAuthResult} from '@/features/auth/api/session';
import {AUTH_SESSION_KEY} from '@/features/auth/api/storage';
import {AUTH_STATE_CHANGE_EVENT} from './shared';

// A session check that fails for a transient reason leaves a valid session unverified,
// and nothing else in the app re-runs it — protected pages would stay unreachable until
// the member reloaded by hand. Retry on a capped exponential backoff instead.
const VERIFY_RETRY_INITIAL_MS = 1_000;
const VERIFY_RETRY_MAX_MS = 30_000;

interface UseSessionSynchronizationOptions {
  applySession: (session: StoredAuthSession | null) => void;
  setUnverified: (unverified: boolean) => void;
  setIsInitializing: (initializing: boolean) => void;
}

const sameIdentity = (left: StoredAuthSession, right: StoredAuthSession) =>
  left.generation === right.generation && left.user.member_uuid === right.user.member_uuid;

/**
 * The session check's state machine: only the latest check may apply its result, a known
 * identity is revalidated quietly, and an inconclusive check is retried with backoff.
 */
function createSessionSynchronizer({
  applySession,
  setUnverified,
  setIsInitializing,
}: UseSessionSynchronizationOptions) {
  let active = true;
  let syncSequence = 0;
  let verifiedSession: StoredAuthSession | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let retryDelay = VERIFY_RETRY_INITIAL_MS;
  const matchesVerifiedIdentity = (session: StoredAuthSession) =>
    verifiedSession !== null && sameIdentity(verifiedSession, session);

  const cancelRetry = () => {
    if (retryTimer === undefined) return;
    clearTimeout(retryTimer);
    retryTimer = undefined;
  };

  const scheduleRetry = () => {
    if (!active || retryTimer !== undefined) return;
    const delay = retryDelay;
    retryDelay = Math.min(retryDelay * 2, VERIFY_RETRY_MAX_MS);
    retryTimer = setTimeout(() => {
      retryTimer = undefined;
      void synchronize();
    }, delay);
  };

  const signedOut = () => {
    verifiedSession = null;
    retryDelay = VERIFY_RETRY_INITIAL_MS;
    applySession(null);
    setUnverified(false);
  };

  /** Apply a finished check to the still-current identity. */
  const applyResult = (current: StoredAuthSession, result: BootstrapAuthResult) => {
    if (result.status === 'verified' && sameIdentity(result.session, current)) {
      verifiedSession = result.session;
    }
    const verified = matchesVerifiedIdentity(current);
    // Keep server-verified flags during transient failures; same-generation
    // local profile edits are not authoritative permission updates.
    applySession(verified ? verifiedSession : current);
    setUnverified(!verified);
    // An unverified result here means the check did not reach a verdict for this
    // generation. A confirmed logout takes the anonymous branch, so this is a
    // transient failure: keep checking rather than stranding a signed-in member.
    if (verified) {
      retryDelay = VERIFY_RETRY_INITIAL_MS;
    } else {
      scheduleRetry();
    }
  };

  const synchronize = async () => {
    const sequence = ++syncSequence;
    cancelRetry();
    const stored = getStoredSession();
    if (!stored) {
      signedOut();
      setIsInitializing(false);
      return;
    }
    const alreadyVerified = matchesVerifiedIdentity(stored);
    if (!alreadyVerified) {
      verifiedSession = null;
      applySession(stored);
    }
    setUnverified(!alreadyVerified);
    setIsInitializing(!alreadyVerified);

    const result = await bootstrapAuthSession();
    if (!active || sequence !== syncSequence) return;
    const current = getStoredSession();
    if (current && !sameIdentity(current, stored)) {
      // Storage can change before its event is delivered. Never apply the
      // previous account's completion to the replacement identity.
      void synchronize();
      return;
    }
    if (!current || result.status === 'anonymous') {
      signedOut();
    } else {
      applyResult(current, result);
    }
    setIsInitializing(false);
  };

  const stop = () => {
    active = false;
    syncSequence += 1;
    cancelRetry();
  };

  return {synchronize, stop};
}

/**
 * Verify the stored session with the server, and re-verify whenever it changes: an
 * `i2g-auth-state-change` event from this tab (any of its React roots) or a storage event
 * from another tab. Only the latest check may apply its result.
 */
export function useSessionSynchronization({
  applySession,
  setUnverified,
  setIsInitializing,
}: UseSessionSynchronizationOptions) {
  // Keep the separate application/menu React roots and other browser tabs on
  // the same persisted generation. Revalidating a known identity is not a
  // logout; a replacement generation must earn its own verification.
  useEffect(() => {
    const {synchronize, stop} = createSessionSynchronizer({applySession, setUnverified, setIsInitializing});
    const handleAuthStateChange = () => void synchronize();
    const handleStorageChange = (event: StorageEvent) => {
      if (event.storageArea && event.storageArea !== localStorage) return;
      if (event.key !== null && event.key !== AUTH_SESSION_KEY) return;
      void synchronize();
    };
    window.addEventListener(
      AUTH_STATE_CHANGE_EVENT,
      handleAuthStateChange,
    );
    window.addEventListener('storage', handleStorageChange);
    void synchronize();
    return () => {
      stop();
      window.removeEventListener(
        AUTH_STATE_CHANGE_EVENT,
        handleAuthStateChange,
      );
      window.removeEventListener('storage', handleStorageChange);
    };
  }, [applySession, setIsInitializing, setUnverified]);
}

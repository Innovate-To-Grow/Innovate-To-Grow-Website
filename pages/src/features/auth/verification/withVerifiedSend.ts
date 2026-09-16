import {VerificationFlowError} from './errors';

import axios, {AxiosError, type AxiosResponse} from 'axios';

import {getStoredSession} from '../api/storage';
import {createSendChallenge, fetchSendRequestStatus} from './api';
import {newRequestId, solveAltchaChallenge} from './solve';
import {setVerifiedSendStatus} from './status';
import type {DestinationKind, SendVerificationFields, SendVerificationOperation} from './types';

const inFlight = new Map<string, Promise<unknown>>();
const pendingRequests = new Map<string, string>();
const storagePrefix = 'i2g_verified_send:';
const unresolvedMessage = 'The previous send request is still unresolved. Please wait, then check your messages before requesting another code.';

function identity(): string {
  return getStoredSession()?.generation ?? 'anonymous';
}

async function contextKey(value: unknown): Promise<string> {
  if (typeof crypto === 'undefined' || !crypto.subtle) {
    throw new VerificationFlowError('Secure verification is unavailable in this browser.');
  }
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(value)));
  return storagePrefix + Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

function readPending(key: string): string | null {
  try {
    return sessionStorage.getItem(key) ?? pendingRequests.get(key) ?? null;
  } catch {
    return pendingRequests.get(key) ?? null;
  }
}

function savePending(key: string, requestId: string | null): void {
  if (requestId) pendingRequests.set(key, requestId);
  else pendingRequests.delete(key);
  try {
    if (requestId) sessionStorage.setItem(key, requestId);
    else sessionStorage.removeItem(key);
  } catch {
    // Keep the in-memory reservation when browser storage is unavailable.
  }
}

function mayHaveSent(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return true;
  return !error.response || error.response.data?.code === 'send_unknown' || error.response.status >= 500;
}

async function reconcile<T>(key: string, requestId: string): Promise<T> {
  let recorded;
  try {
    recorded = await fetchSendRequestStatus(requestId);
  } catch (error) {
    throw new VerificationFlowError(unresolvedMessage, {cause: error});
  }
  if (recorded.status === 'provider_accepted' || recorded.status === 'submitted') {
    savePending(key, null);
    return recorded.result as T;
  }
  if (recorded.status === 'definitely_failed') {
    savePending(key, null);
    throw new AxiosError(
      typeof recorded.result.detail === 'string' ? recorded.result.detail : 'The code could not be sent. Please try again.',
      undefined, undefined, undefined,
      {data: recorded.result, status: recorded.http_status} as AxiosResponse,
    );
  }
  throw new VerificationFlowError(unresolvedMessage);
}

export async function withVerifiedSend<T>(options: {
  operation: SendVerificationOperation;
  destinationKind: DestinationKind;
  destination: string;
  extraChallenge?: Record<string, string | undefined>;
  signal?: AbortSignal;
  execute: (verification: SendVerificationFields) => Promise<T>;
}): Promise<T> {
  const startedIdentity = identity();
  const context = Object.entries(options.extraChallenge ?? {}).sort(([left], [right]) => left.localeCompare(right));
  const flightKey = JSON.stringify([startedIdentity, options.operation, options.destinationKind, options.destination, context]);
  options.signal?.throwIfAborted();
  const existing = inFlight.get(flightKey);
  if (existing) return existing as Promise<T>;

  const run = (async () => {
    const controller = new AbortController();
    const abort = () => controller.abort();
    const checkIdentity = () => {
      if (identity() !== startedIdentity) controller.abort();
    };
    options.signal?.addEventListener('abort', abort, {once: true});
    window.addEventListener('i2g-auth-state-change', checkIdentity);
    window.addEventListener('storage', checkIdentity);
    try {
      const key = await contextKey(flightKey);
      checkIdentity();
      controller.signal.throwIfAborted();
      const pendingId = readPending(key);
      if (pendingId) {
        setVerifiedSendStatus({phase: 'sending', message: 'Checking the previous request…'});
        const result = await reconcile<T>(key, pendingId);
        controller.signal.throwIfAborted();
        setVerifiedSendStatus({phase: 'idle', message: ''});
        return result;
      }
      const sendRequestId = newRequestId();
      setVerifiedSendStatus({phase: 'challenging', message: 'Preparing verification…'});
      const challenge = await createSendChallenge({
        operation: options.operation,
        destination: options.destination,
        destination_kind: options.destinationKind,
        ...options.extraChallenge,
      }, controller.signal);
      checkIdentity();
      controller.signal.throwIfAborted();
      setVerifiedSendStatus({phase: 'solving', message: 'Verifying this request…'});
      const payload = await solveAltchaChallenge(challenge.challenge, controller.signal);
      checkIdentity();
      controller.signal.throwIfAborted();
      const verification: SendVerificationFields = {
        verification_challenge_id: challenge.challenge_id,
        verification_payload: payload,
        send_request_id: sendRequestId,
      };
      setVerifiedSendStatus({phase: 'sending', message: 'Sending verification code…'});
      // Save before dispatch: a reload or navigation must not start another send.
      savePending(key, sendRequestId);
      try {
        const result = await options.execute(verification);
        savePending(key, null);
        setVerifiedSendStatus({phase: 'idle', message: ''});
        return result;
      } catch (error) {
        if (mayHaveSent(error)) {
          const result = await reconcile<T>(key, sendRequestId);
          setVerifiedSendStatus({phase: 'idle', message: ''});
          return result;
        }
        savePending(key, null);
        throw error;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Verification failed. Please try again.';
      setVerifiedSendStatus({phase: 'error', message});
      throw error;
    } finally {
      options.signal?.removeEventListener('abort', abort);
      window.removeEventListener('i2g-auth-state-change', checkIdentity);
      window.removeEventListener('storage', checkIdentity);
      inFlight.delete(flightKey);
    }
  })();
  inFlight.set(flightKey, run);
  return run;
}

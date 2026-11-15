import {VerificationFlowError} from './types';

import axios, {AxiosError, type AxiosResponse} from 'axios';

import {fetchSendRequestStatus} from './api';

const pendingRequests = new Map<string, string>();
const storagePrefix = 'i2g_verified_send:';
const unresolvedMessage = 'The previous send request is still unresolved. Please wait, then check your messages before requesting another code.';

export async function contextKey(value: unknown): Promise<string> {
  if (typeof crypto === 'undefined' || !crypto.subtle) {
    throw new VerificationFlowError('Secure verification is unavailable in this browser.');
  }
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(value)));
  return storagePrefix + Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function readPending(key: string): string | null {
  try {
    return sessionStorage.getItem(key) ?? pendingRequests.get(key) ?? null;
  } catch {
    return pendingRequests.get(key) ?? null;
  }
}

export function savePending(key: string, requestId: string | null): void {
  if (requestId) pendingRequests.set(key, requestId);
  else pendingRequests.delete(key);
  try {
    if (requestId) sessionStorage.setItem(key, requestId);
    else sessionStorage.removeItem(key);
  } catch {
    // Keep the in-memory reservation when browser storage is unavailable.
  }
}

export function mayHaveSent(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return true;
  return !error.response || error.response.data?.code === 'send_unknown' || error.response.status >= 500;
}

export async function reconcile<T>(key: string, requestId: string): Promise<T> {
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

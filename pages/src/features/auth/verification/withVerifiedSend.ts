import {getStoredSession} from '../api/session/storage';
import {createSendChallenge} from './api';
import {newRequestId, solveAltchaChallenge} from './solve';
import {setVerifiedSendStatus} from './status';
import type {DestinationKind, SendVerificationFields, SendVerificationOperation} from './types';
import {contextKey, mayHaveSent, readPending, reconcile, savePending} from './pendingSend';

const inFlight = new Map<string, Promise<unknown>>();

/**
 * Whether the server binds an operation's challenge to the signed-in member.
 * This mirrors `AUTHENTICATED_OPERATIONS` in
 * `apps/authn/services/send_verification/rules/constants.py`. Every other operation
 * is bound to the browser's Django session cookie and never looks at the JWT
 * session. Typed as a complete record so a new operation cannot be added
 * without deciding which kind it is.
 */
const MEMBER_BOUND: Record<SendVerificationOperation, boolean> = {
  'email_auth.request_code': false,
  'phone_auth.request_code': false,
  'login.request_code': false,
  register: false,
  'register.resend_code': false,
  'password_reset.request_code': false,
  'change_password.request_code': true,
  'delete_account.request_code': true,
  'contact_email.create': true,
  'contact_email.request_verification': true,
  'contact_phone.request_verification': true,
  'event.send_phone_code': true,
  'event.send_secondary_email_code': true,
  'admin.login.request_code': false,
  'admin.login.remembered_code': false,
  'admin.login.resend': false,
};

/**
 * Who a send acts for. A member-bound operation is tied to the stored session
 * generation, so switching or clearing the account cancels it. An anonymous one
 * has a single constant identity: the stored session is irrelevant to it, and
 * must stay so — a browser holding a dead session has it cleared by the auth
 * bootstrap while a code request is still in flight, and that must not abort
 * the request.
 */
function identity(operation: SendVerificationOperation): string {
  if (!MEMBER_BOUND[operation]) return 'anonymous';
  return getStoredSession()?.generation ?? 'anonymous';
}

interface VerifiedSendOptions<T> {
  operation: SendVerificationOperation;
  destinationKind: DestinationKind;
  destination: string;
  extraChallenge?: Record<string, string | undefined>;
  signal?: AbortSignal;
  execute: (verification: SendVerificationFields) => Promise<T>;
}

/** Solve a new challenge and send with it; a send that may have gone out is reconciled, never repeated. */
async function sendWithFreshChallenge<T>(
  options: VerifiedSendOptions<T>,
  key: string,
  signal: AbortSignal,
  checkIdentity: () => void,
): Promise<T> {
  const sendRequestId = newRequestId();
  setVerifiedSendStatus({phase: 'challenging', message: 'Preparing verification…'});
  const challenge = await createSendChallenge({
    operation: options.operation,
    destination: options.destination,
    destination_kind: options.destinationKind,
    ...options.extraChallenge,
  }, signal);
  checkIdentity();
  signal.throwIfAborted();
  setVerifiedSendStatus({phase: 'solving', message: 'Verifying this request…'});
  const payload = await solveAltchaChallenge(challenge.challenge, signal);
  checkIdentity();
  signal.throwIfAborted();
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
}

export async function withVerifiedSend<T>(options: VerifiedSendOptions<T>): Promise<T> {
  const startedIdentity = identity(options.operation);
  const context = Object.entries(options.extraChallenge ?? {}).sort(([left], [right]) => left.localeCompare(right));
  const flightKey = JSON.stringify([startedIdentity, options.operation, options.destinationKind, options.destination, context]);
  options.signal?.throwIfAborted();
  const existing = inFlight.get(flightKey);
  if (existing) return existing as Promise<T>;

  const run = (async () => {
    const controller = new AbortController();
    const abort = () => controller.abort();
    const checkIdentity = () => {
      if (identity(options.operation) !== startedIdentity) controller.abort();
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
      return await sendWithFreshChallenge(options, key, controller.signal, checkIdentity);
    } catch (error) {
      // The caller shows the server's actionable error beside the form. Clear
      // progress here so a transport error is never left in the global status.
      setVerifiedSendStatus({phase: 'idle', message: ''});
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

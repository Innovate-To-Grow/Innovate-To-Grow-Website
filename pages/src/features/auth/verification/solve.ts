import {VerificationFlowError} from './errors';

import type {AltchaWidgetElement} from 'altcha';
import type {Challenge} from 'altcha/types';

import {loadAltcha} from './loadAltcha';

export function newRequestId(): string {
  if (typeof crypto === 'undefined' || typeof crypto.getRandomValues !== 'function') {
    throw new VerificationFlowError('Secure verification is unavailable in this browser.');
  }
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const verificationFailed = () => new VerificationFlowError('Verification failed. Please try again.');

/** An off-screen ALTCHA widget that only runs when told to. */
function createHiddenWidget(): {host: HTMLDivElement; widget: AltchaWidgetElement} {
  const host = document.createElement('div');
  host.style.position = 'absolute';
  host.style.left = '-9999px';
  const widget: AltchaWidgetElement = document.createElement('altcha-widget');
  widget.setAttribute('auto', 'off');
  return {host, widget};
}

const SUPERSEDED = Symbol('superseded');

/** Configure the widget with the signed challenge and solve it; SUPERSEDED when the attempt settled meanwhile. */
async function configureAndVerify(
  widget: AltchaWidgetElement,
  challenge: Record<string, unknown>,
  isSettled: () => boolean,
) {
  await widget.configure({challenge: challenge as unknown as Challenge, auto: 'off', hideFooter: true, hideLogo: true});
  if (isSettled()) return SUPERSEDED;
  // Avoid terminating sibling workers while their WebCrypto jobs are active.
  // One worker still searches every counter at the signed challenge cost.
  const result = await widget.verify({concurrency: 1});
  return isSettled() ? SUPERSEDED : result;
}

const settle = (resolve: (payload: string) => void, reject: (error: Error) => void, error?: Error, payload?: string) => {
  if (error) reject(error);
  else if (payload) resolve(payload);
  else reject(new VerificationFlowError('Verification did not produce a payload.'));
};

/** One verification attempt in an off-screen widget; settles exactly once (payload, error, timeout or abort). */
function attemptVerification(
  challenge: Record<string, unknown>,
  signal: AbortSignal | undefined,
  resolve: (payload: string) => void,
  reject: (error: Error) => void,
) {
  const {host, widget} = createHiddenWidget();
  let settled = false;
  let started = false;
  const timeout = window.setTimeout(() => {
    finish(new VerificationFlowError('Verification timed out. Please try again.'));
  }, 90_000);
  const finish = (error?: Error, payload?: string) => {
    if (settled) return;
    settled = true;
    window.clearTimeout(timeout);
    for (const [type, listener] of Object.entries(listeners)) widget.removeEventListener(type, listener);
    signal?.removeEventListener('abort', aborted);
    host.remove();
    settle(resolve, reject, error, payload);
  };
  const aborted = () => finish(new DOMException('Aborted', 'AbortError'));
  const start = () => {
    if (started || settled || typeof widget.configure !== 'function' || typeof widget.verify !== 'function') return;
    started = true;
    configureAndVerify(widget, challenge, () => settled).then(
      (result) => {
        if (result !== SUPERSEDED) finish(result ? undefined : verificationFailed(), result?.payload);
      },
      (error: unknown) => finish(error instanceof Error ? error : verificationFailed()),
    );
  };
  const listeners: Record<string, (event: Event) => void> = {
    load: start,
    verified: (event) => finish(undefined, (event as CustomEvent<{payload?: string}>).detail?.payload),
    statechange: (event) => {
      if ((event as CustomEvent<{state?: string}>).detail?.state === 'error') finish(verificationFailed());
    },
  };
  for (const [type, listener] of Object.entries(listeners)) widget.addEventListener(type, listener);
  signal?.addEventListener('abort', aborted, {once: true});
  host.appendChild(widget);
  document.body.appendChild(host);
  start();
  if (signal?.aborted) aborted();
}

export async function solveAltchaChallenge(
  challenge: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<string> {
  signal?.throwIfAborted();
  await loadAltcha();
  signal?.throwIfAborted();
  return new Promise((resolve, reject) => attemptVerification(challenge, signal, resolve, reject));
}

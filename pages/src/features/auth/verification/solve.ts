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

export async function solveAltchaChallenge(
  challenge: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<string> {
  signal?.throwIfAborted();
  await loadAltcha();
  signal?.throwIfAborted();
  return new Promise((resolve, reject) => {
    const host = document.createElement('div');
    host.style.position = 'absolute';
    host.style.left = '-9999px';
    const widget: AltchaWidgetElement = document.createElement('altcha-widget');
    widget.setAttribute('auto', 'off');
    let settled = false;
    let started = false;
    const timeout = window.setTimeout(() => {
      finish(new VerificationFlowError('Verification timed out. Please try again.'));
    }, 90_000);
    const finish = (error?: Error, payload?: string) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeout);
      widget.removeEventListener('load', start);
      widget.removeEventListener('verified', verified);
      widget.removeEventListener('statechange', stateChanged);
      signal?.removeEventListener('abort', aborted);
      host.remove();
      if (error) reject(error);
      else if (payload) resolve(payload);
      else reject(new VerificationFlowError('Verification did not produce a payload.'));
    };
    const aborted = () => finish(new DOMException('Aborted', 'AbortError'));
    const verified = (event: Event) => {
      const detail = (event as CustomEvent<{payload?: string}>).detail;
      finish(undefined, detail?.payload);
    };
    const stateChanged = (event: Event) => {
      if ((event as CustomEvent<{state?: string}>).detail?.state === 'error') {
        finish(new VerificationFlowError('Verification failed. Please try again.'));
      }
    };
    const start = () => {
      if (started || settled || typeof widget.configure !== 'function' || typeof widget.verify !== 'function') return;
      started = true;
      void (async () => {
        await widget.configure({challenge: challenge as unknown as Challenge, auto: 'off', hideFooter: true, hideLogo: true});
        if (settled) return;
        const result = await widget.verify();
        if (!settled) finish(result ? undefined : new VerificationFlowError('Verification failed. Please try again.'), result?.payload);
      })().catch((error: unknown) => finish(error instanceof Error ? error : new VerificationFlowError('Verification failed. Please try again.')));
    };
    widget.addEventListener('load', start);
    widget.addEventListener('verified', verified);
    widget.addEventListener('statechange', stateChanged);
    signal?.addEventListener('abort', aborted, {once: true});
    host.appendChild(widget);
    document.body.appendChild(host);
    start();
    if (signal?.aborted) aborted();
  });
}

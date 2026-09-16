import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {waitFor} from '@testing-library/react';
import {webcrypto} from 'node:crypto';

vi.mock('@/features/auth/verification/loadAltcha', () => ({loadAltcha: vi.fn(async () => undefined)}));

import {loadAltcha} from '@/features/auth/verification/loadAltcha';
import {newRequestId, solveAltchaChallenge} from '@/features/auth/verification/solve';

const configure = vi.fn<() => Promise<void>>();
const verify = vi.fn<() => Promise<{payload: string} | null>>();
let ready = true;

class DeferredWidget extends HTMLElement {
  connectedCallback() {
    // Match custom-element upgrades: registration precedes instance methods.
    if (ready) queueMicrotask(() => {
      Object.assign(this, {configure, verify});
      this.dispatchEvent(new Event('load'));
    });
  }
}
if (!customElements.get('altcha-widget')) customElements.define('altcha-widget', DeferredWidget);

beforeEach(() => {
  ready = true;
  vi.stubGlobal('crypto', webcrypto);
  vi.mocked(loadAltcha).mockReset().mockResolvedValue(undefined);
  configure.mockReset().mockResolvedValue(undefined);
  verify.mockReset().mockResolvedValue({payload: 'proof'});
});
afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('ALTCHA instance lifecycle', () => {
  it('waits for instance load and configuration before verification', async () => {
    let configured: (() => void) | undefined;
    configure.mockImplementation(() => new Promise<void>((resolve) => {configured = resolve;}));
    const result = solveAltchaChallenge({parameters: {cost: 1}});
    await waitFor(() => expect(configure).toHaveBeenCalled());
    expect(verify).not.toHaveBeenCalled();
    configured!();
    await expect(result).resolves.toBe('proof');
    expect(verify).toHaveBeenCalledTimes(1);
    expect(document.querySelector('altcha-widget')).toBeNull();
  });

  it('uses the verified payload event and tolerates a later null result', async () => {
    verify.mockImplementation(async () => {
      document.querySelector('altcha-widget')!.dispatchEvent(new CustomEvent('statechange', {detail: {state: 'verifying'}}));
      document.querySelector('altcha-widget')!.dispatchEvent(new CustomEvent('verified', {detail: {payload: 'event-proof'}}));
      return null;
    });
    await expect(solveAltchaChallenge({})).resolves.toBe('event-proof');
    expect(document.querySelector('altcha-widget')).toBeNull();
  });

  it('rejects an actual error state immediately', async () => {
    verify.mockImplementation(async () => {
      document.querySelector('altcha-widget')!.dispatchEvent(new CustomEvent('statechange', {detail: {state: 'error'}}));
      return null;
    });
    await expect(solveAltchaChallenge({})).rejects.toThrow('Verification failed');
    expect(document.querySelector('altcha-widget')).toBeNull();
  });

  it('rejects missing verified payloads', async () => {
    verify.mockImplementation(async () => {
      document.querySelector('altcha-widget')!.dispatchEvent(new CustomEvent('verified', {detail: {}}));
      return null;
    });
    await expect(solveAltchaChallenge({})).rejects.toThrow('did not produce a payload');
  });

  it('rejects a null solver result', async () => {
    verify.mockResolvedValue(null);
    await expect(solveAltchaChallenge({})).rejects.toThrow('Verification failed');
  });

  it.each([new Error('worker stopped'), 'unexpected rejection'])('cleans up after rejected configuration', async (reason) => {
    configure.mockRejectedValue(reason);
    await expect(solveAltchaChallenge({})).rejects.toThrow(reason instanceof Error ? 'worker stopped' : 'Verification failed');
    expect(verify).not.toHaveBeenCalled();
    expect(document.querySelector('altcha-widget')).toBeNull();
  });

  it('bounds instances that never become ready', async () => {
    vi.useFakeTimers();
    ready = false;
    const result = solveAltchaChallenge({});
    const rejected = expect(result).rejects.toThrow('timed out');
    await vi.advanceTimersByTimeAsync(90_000);
    await rejected;
    expect(verify).not.toHaveBeenCalled();
    expect(document.querySelector('altcha-widget')).toBeNull();
  });

  it('cancels during configuration and does not start the worker afterwards', async () => {
    const controller = new AbortController();
    let configured: (() => void) | undefined;
    configure.mockImplementation(() => new Promise<void>((resolve) => {configured = resolve;}));
    const result = solveAltchaChallenge({}, controller.signal);
    const rejected = expect(result).rejects.toMatchObject({name: 'AbortError'});
    await waitFor(() => expect(configure).toHaveBeenCalled());
    controller.abort();
    await rejected;
    configured!();
    await Promise.resolve();
    expect(verify).not.toHaveBeenCalled();
    expect(document.querySelector('altcha-widget')).toBeNull();
  });

  it('cancels before asset loading', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(solveAltchaChallenge({}, controller.signal)).rejects.toMatchObject({name: 'AbortError'});
    expect(loadAltcha).not.toHaveBeenCalled();
  });

  it('does not create a widget after an asset failure', async () => {
    vi.mocked(loadAltcha).mockRejectedValue(new Error('Asset unavailable'));
    await expect(solveAltchaChallenge({})).rejects.toThrow('Asset unavailable');
    expect(document.querySelector('altcha-widget')).toBeNull();
  });
});

describe('request identifiers', () => {
  it('uses secure UUIDs', () => {
    expect(newRequestId()).toMatch(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
  });
  it('uses secure random bytes when randomUUID is unavailable', () => {
    let counter = 0;
    vi.stubGlobal('crypto', {getRandomValues: (bytes: Uint8Array) => bytes.fill(++counter)});
    expect(newRequestId()).toBe('01010101-0101-4101-8101-010101010101');
    expect(newRequestId()).toBe('02020202-0202-4202-8202-020202020202');
  });
  it.each([undefined, {}])('fails closed without secure random support', (cryptoValue) => {
    vi.stubGlobal('crypto', cryptoValue);
    expect(newRequestId).toThrow('Secure verification is unavailable');
  });
});

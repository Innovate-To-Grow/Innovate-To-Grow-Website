// admin/js/poll-backoff.js and the admin status pages that poll with it: campaign and SMS send status, Delivery
// Rates and Request Limits. A 429 pauses polling for the server's Retry-After instead of being read as a status.
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {installPollBackoff, jsonResponse} from '@/__tests__/core/adminStatic';

interface Gate {
  blocked(): boolean;
  remainingMs(): number;
  refused(serverWaitMs?: number | null): number;
  succeeded(): void;
  strikes(): number;
}

interface PollBackoff {
  createGate(options?: {baseMs?: number; maxMs?: number; now?: () => number}): Gate;
  parseRetryAfter(value: unknown, now?: number): number | null;
  retryAfterMs(response: unknown, data?: unknown): number | null;
  waitText(ms: number | null | undefined): string;
}

const backoff = () => (window as unknown as {I2GPollBackoff: PollBackoff}).I2GPollBackoff;
const fetchMock = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-02T12:00:00Z'));
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
  installPollBackoff();
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
  delete (window as unknown as {I2GPollBackoff?: PollBackoff}).I2GPollBackoff;
});

describe('I2GPollBackoff', () => {
  it('parses delta-seconds and HTTP dates, and rejects the rest', () => {
    const {parseRetryAfter} = backoff();
    const now = Date.parse('2026-11-02T12:00:00Z');
    expect(parseRetryAfter('5')).toBe(5000);
    expect(parseRetryAfter(' 0.5 ')).toBe(500);
    expect(parseRetryAfter('Mon, 02 Nov 2026 12:00:03 GMT', now)).toBe(3000);
    expect(parseRetryAfter('Mon, 02 Nov 2026 11:00:00 GMT')).toBeNull();
    expect(parseRetryAfter('later')).toBeNull();
    expect(parseRetryAfter('')).toBeNull();
    expect(parseRetryAfter(null)).toBeNull();
    expect(parseRetryAfter(undefined)).toBeNull();
  });

  it('reads the wait from the header, a plain headers object, or the body', () => {
    const {retryAfterMs} = backoff();
    expect(retryAfterMs(jsonResponse(429, {}, {'Retry-After': '4'}), {retry_after: 9})).toBe(4000);
    expect(retryAfterMs({headers: {'retry-after': '2'}})).toBe(2000);
    expect(retryAfterMs({headers: {'Retry-After': '3'}})).toBe(3000);
    expect(retryAfterMs({headers: {}}, {retry_after: 6})).toBe(6000);
    expect(retryAfterMs(jsonResponse(429, {}), {retry_after: 'soon'})).toBeNull();
    expect(retryAfterMs(null, {retry_after: -1})).toBeNull();
    expect(retryAfterMs(undefined, 'text')).toBeNull();
  });

  it('words a wait in whole seconds', () => {
    const {waitText} = backoff();
    expect(waitText(null)).toBe('in a moment');
    expect(waitText(undefined)).toBe('in a moment');
    expect(waitText(200)).toBe('in 1 second');
    expect(waitText(4100)).toBe('in 5 seconds');
  });

  it('blocks for the larger of the server wait and the doubling back-off, capped, until a success', () => {
    let clock = 0;
    const gate = backoff().createGate({baseMs: 1000, maxMs: 10_000, now: () => clock});

    expect(gate.blocked()).toBe(false);
    expect(gate.refused(5000)).toBe(5000);
    expect(gate.blocked()).toBe(true);
    expect(gate.remainingMs()).toBe(5000);
    expect(gate.refused(null)).toBe(4000);
    expect(gate.refused(undefined)).toBe(8000);
    expect(gate.refused(0)).toBe(10_000);
    expect(gate.refused(30_000)).toBe(30_000);
    expect(gate.strikes()).toBe(5);
    clock = 30_000;
    expect(gate.blocked()).toBe(false);
    expect(gate.remainingMs()).toBe(0);

    gate.refused(null);
    gate.succeeded();
    expect(gate.blocked()).toBe(false);
    expect(gate.strikes()).toBe(0);
  });

  it('defaults to a 2 s base, a 60 s cap and the real clock', () => {
    const gate = backoff().createGate();
    expect(gate.refused(null)).toBe(4000);
    for (let index = 0; index < 10; index += 1) gate.refused(null);
    expect(gate.refused(null)).toBe(60_000);
    vi.advanceTimersByTime(59_999);
    expect(gate.blocked()).toBe(true);
    vi.advanceTimersByTime(1);
    expect(gate.blocked()).toBe(false);
  });
});

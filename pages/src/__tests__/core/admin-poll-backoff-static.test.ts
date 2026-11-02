// admin/js/poll-backoff.js and the admin status pages that poll with it: campaign and SMS send status, Delivery
// Rates and Request Limits. A 429 pauses polling for the server's Retry-After instead of being read as a status.
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {flush, inlineScripts, installPollBackoff, jsonResponse, templateMarkup} from '@/__tests__/core/adminStatic';

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

const SEND_STATUS_PAGES = [
  ['campaign', 'src/apps/mail/templates/admin/mail/send_status.html', 'Campaign Sent'],
  ['SMS campaign', 'src/apps/mail/templates/admin/mail/smscampaign/send_status.html', 'SMS Campaign Sent'],
] as const;

describe.each(SEND_STATUS_PAGES)('%s send status polling', (_name, template, sentText) => {
  const vars = {status_json_url: '/admin/status/', 'campaign.total_recipients': '2'};

  const open = () => {
    document.body.innerHTML = templateMarkup(template, 'content', vars);
    for (const script of inlineScripts(template, vars)) window.eval(script);
  };

  it('keeps the last status after a 429, waits out Retry-After, then resumes until the send finishes', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(429, {detail: 'Too many requests.', retry_after: 5}, {'Retry-After': '5'}))
      .mockResolvedValueOnce(jsonResponse(200, {status: 'sending', sent: 1, failed: 0}))
      .mockResolvedValue(jsonResponse(200, {status: 'sent', sent: 2, failed: 0}));

    open();
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(document.getElementById('status-text')?.textContent).toBe('Sending...');

    await vi.advanceTimersByTimeAsync(4000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(document.getElementById('status-text')?.textContent).toBe('Sending...');

    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(document.getElementById('status-text')?.textContent).toBe(sentText);

    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('copes with a 429 whose body is not JSON, backing off by the doubling wait', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response('busy', {status: 429}))
      .mockResolvedValue(jsonResponse(200, {status: 'sending', sent: 0, failed: 0}));

    open();
    await flush();
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('still ignores a 429 when the back-off helper did not load', async () => {
    delete (window as unknown as {I2GPollBackoff?: PollBackoff}).I2GPollBackoff;
    fetchMock
      .mockResolvedValueOnce(jsonResponse(429, {detail: 'Too many requests.'}))
      .mockResolvedValue(jsonResponse(200, {status: 'sending', sent: 0, failed: 0}));

    open();
    await flush();
    await vi.advanceTimersByTimeAsync(1000);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(document.getElementById('status-text')?.textContent).toBe('Sending...');
  });
});

const STATUS_PAGES = [
  ['Delivery Rates', 'src/apps/mail/templates/admin/mail/settings_rates.html'],
  ['Request Limits', 'src/apps/core/templates/admin/core/request_limits.html'],
] as const;

describe.each(STATUS_PAGES)('%s status refresh', (_name, template) => {
  const vars = {status_url: '/admin/rates/status/', status_refresh_ms: '1000'};

  const open = () => {
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
    document.body.innerHTML = templateMarkup(template, 'content', vars);
    for (const script of inlineScripts(template, vars)) window.eval(script);
  };

  it('pauses refreshes for the Retry-After of a 429, then resumes', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(429, {retry_after: 3}, {'Retry-After': '3'}))
      .mockResolvedValue(jsonResponse(200, {channels: [], scopes: [], summary: {}}));

    open();
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(2000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('waits the doubling back-off when the 429 body is not JSON', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response('busy', {status: 429}))
      .mockResolvedValue(jsonResponse(200, {channels: [], scopes: [], summary: {}}));

    open();
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('keeps refreshing on its interval without the helper, skipping the 429', async () => {
    delete (window as unknown as {I2GPollBackoff?: PollBackoff}).I2GPollBackoff;
    fetchMock
      .mockResolvedValueOnce(jsonResponse(429, {}))
      .mockResolvedValue(jsonResponse(200, {channels: [], scopes: [], summary: {}}));

    open();
    await vi.advanceTimersByTimeAsync(2000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

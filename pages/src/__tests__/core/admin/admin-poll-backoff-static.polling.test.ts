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
  ['Request Limits', 'src/apps/core/templates/admin/core/request_limits/request_limits.html'],
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

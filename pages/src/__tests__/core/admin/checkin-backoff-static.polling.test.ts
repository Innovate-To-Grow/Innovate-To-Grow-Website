// The event check-in console (scanner.html + checkin_*.js) and the check-in change-form summary under 429: a refused
// scan reads "Busy — retry" (nothing was checked in) rather than "Unable to check in", and status polling pauses for
// the server's Retry-After.
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {flush, installPollBackoff, jsonResponse, readRepoFile, templateMarkup} from '@/__tests__/core/adminStatic';

const JS = 'src/apps/event/static/event/js/checkin/';
const CONSOLE_SCRIPTS = ['checkin_shared.js', 'checkin_ticket_input.js', 'checkin_camera.js', 'checkin_console.js'];
const SCAN_URL = '/event/check-in/c1/scan/';
const STATUS_URL = '/event/check-in/c1/status/';
const fetchMock = vi.fn();
const listeners: Array<[EventTarget, string, EventListenerOrEventListenerObject]> = [];
const status = {total: 2, scanned: 1, not_checked_in: [{name: 'Ada', ticket_code: 'T1'}], recent_scans: []};
const refused = (seconds?: string) =>
  jsonResponse(429, {detail: 'Too many requests.', code: 'rate_limited'}, seconds ? {'Retry-After': seconds} : {});

/** Answer each URL with its queued responses, the last one repeating. */
function route(answers: Record<string, Response[]>) {
  fetchMock.mockImplementation(async (url: string) => {
    const queue = answers[url];
    if (!queue?.length) throw new Error(`unexpected fetch ${url}`);
    return (queue.length > 1 ? queue.shift() : queue[0])!.clone();
  });
}

const callsTo = (url: string) => fetchMock.mock.calls.filter(([called]) => called === url).length;
const text = (selector: string) => document.querySelector(selector)?.textContent ?? '';

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  for (const target of [document, window] as EventTarget[]) {
    const add = target.addEventListener.bind(target);
    vi.spyOn(target, 'addEventListener').mockImplementation((type, listener, options) => {
      listeners.push([target, type, listener as EventListenerOrEventListenerObject]);
      add(type, listener, options);
    });
  }
});

afterEach(() => {
  for (const [target, type, listener] of listeners.splice(0)) target.removeEventListener(type, listener);
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
  delete (window as {I2GPollBackoff?: unknown}).I2GPollBackoff;
  delete (window as {__checkinConsole?: unknown}).__checkinConsole;
});

async function openConsole({helper = true} = {}) {
  document.body.innerHTML = templateMarkup('src/apps/event/templates/admin/event/checkin/scanner.html', 'content');
  const config = document.createElement('script');
  config.id = 'checkin-console-config';
  config.type = 'application/json';
  config.textContent = JSON.stringify({
    scanUrl: SCAN_URL, statusUrl: STATUS_URL, undoUrlTemplate: '/event/check-in/c1/records/__record_id__/undo/',
    statusPollIntervalMs: 2000, csrfToken: 'token',
  });
  document.body.prepend(config);
  if (helper) installPollBackoff();
  for (const name of CONSOLE_SCRIPTS) window.eval(readRepoFile(JS + name));
  document.dispatchEvent(new Event('DOMContentLoaded'));
  await flush();
}

describe('check-in console status polling', () => {
  it('pauses for Retry-After after a 429 and resumes live sync', async () => {
    route({[STATUS_URL]: [jsonResponse(200, status), refused('5'), jsonResponse(200, status)]});
    await openConsole();
    expect(text('[data-sync-label]')).toContain('Live sync');

    await vi.advanceTimersByTimeAsync(2000);
    expect(callsTo(STATUS_URL)).toBe(2);
    expect(text('[data-sync-label]')).toBe('Busy · retrying in 5 seconds');

    await vi.advanceTimersByTimeAsync(4000);
    expect(callsTo(STATUS_URL)).toBe(2);
    await vi.advanceTimersByTimeAsync(2000);
    expect(callsTo(STATUS_URL)).toBe(3);
    expect(text('[data-sync-label]')).toContain('Live sync');
  });

  it('a manual refresh is not held back by the pause', async () => {
    route({[STATUS_URL]: [refused('30'), jsonResponse(200, status)]});
    await openConsole();
    expect(callsTo(STATUS_URL)).toBe(1);

    document.querySelector<HTMLButtonElement>('[data-refresh-button]')!.click();
    await flush(20);

    expect(callsTo(STATUS_URL)).toBe(2);
    expect(text('[data-sync-label]')).toContain('Live sync');
  });

  it('reports a sync issue for a 429 when the helper did not load', async () => {
    route({[STATUS_URL]: [refused('5')]});
    await openConsole({helper: false});

    expect(text('[data-sync-label]')).toBe('Sync issue · retrying');
  });
});

describe('check-in change-form summary polling', () => {
  const SUMMARY_JS = readRepoFile(JS + 'checkin_change_summary.js');
  const summary = {total: 1, scanned: 0, registrations: [], recent_scans: []};

  function openSummary({helper = true} = {}) {
    document.body.innerHTML = templateMarkup('src/apps/event/templates/admin/event/checkin/change_form.html', 'field_sets');
    const config = document.createElement('script');
    config.id = 'checkin-summary-config';
    config.type = 'application/json';
    config.textContent = JSON.stringify({statusUrl: STATUS_URL, pollIntervalMs: 2000});
    document.body.prepend(config);
    if (helper) installPollBackoff();
    window.eval(SUMMARY_JS);
  }

  it('shows that the server is busy before the first load, then loads after the wait', async () => {
    route({[STATUS_URL]: [refused('3'), jsonResponse(200, summary)]});
    openSummary();
    await flush(20);

    expect(text('[data-summary-sync-label]')).toBe('Busy - retrying in 4 seconds');
    expect(text('[data-summary-recent-list]')).toBe('The server is busy; the status loads shortly.');

    await vi.advanceTimersByTimeAsync(2000);
    expect(callsTo(STATUS_URL)).toBe(1);
    await vi.advanceTimersByTimeAsync(2000);
    expect(callsTo(STATUS_URL)).toBe(2);
    expect(text('[data-summary-sync-label]')).toContain('Live - updated');
  });

  it('keeps the old error text for other failures and without the helper', async () => {
    route({[STATUS_URL]: [refused('3')]});
    openSummary({helper: false});
    await flush(20);

    expect(text('[data-summary-sync-label]')).toBe('Sync issue - retrying');
    expect(text('[data-summary-recent-list]')).toBe('Unable to load status: Too many requests.');
  });
});

// The event check-in console (scanner.html + checkin_*.js) and the check-in change-form summary under 429: a refused
// scan reads "Busy — retry" (nothing was checked in) rather than "Unable to check in", and status polling pauses for
// the server's Retry-After.
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {flush, installPollBackoff, jsonResponse, readRepoFile, templateMarkup} from '@/__tests__/core/adminStatic';

const JS = 'src/apps/event/static/event/js/checkin/';
const CONSOLE_SCRIPTS = ['checkin_shared.js', 'checkin_ticket_input.js', 'checkin_camera.js', 'checkin_console.js'];
const SCAN_URL = '/event/check-in/c1/scan/';
const STATUS_URL = '/event/check-in/c1/status/';
const UNDO_URL = '/event/check-in/c1/records/r1/undo/';

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

async function scan(code: string) {
  const input = document.querySelector<HTMLInputElement>('[data-scan-input]')!;
  input.value = code;
  document.querySelector<HTMLFormElement>('[data-scan-form]')!.dispatchEvent(new Event('submit', {cancelable: true}));
  await flush(20);
}

describe('check-in console scan', () => {
  it('shows "Busy — retry" with the wait for a refused scan, not "Unable to check in"', async () => {
    route({[STATUS_URL]: [jsonResponse(200, status)], [SCAN_URL]: [refused('5')]});
    await openConsole();

    await scan('T1');

    const result = document.querySelector('[data-scan-result]')!;
    expect(result.className).toContain('is-busy');
    expect(result.querySelector('strong')?.textContent).toBe('Busy — retry');
    expect(result.textContent).toContain('The server is busy. Try again in 5 seconds.');
    expect(result.textContent).not.toContain('Unable to check in');
    expect(document.querySelector<HTMLButtonElement>('[data-scan-button]')!.disabled).toBe(false);
  });

  it('says "in a moment" when the refusal names no wait, and still works without the helper', async () => {
    route({[STATUS_URL]: [jsonResponse(200, status)], [SCAN_URL]: [refused()]});
    await openConsole({helper: false});

    await scan('T1');

    expect(text('[data-scan-result] strong')).toBe('Busy — retry');
    expect(text('[data-scan-result]')).toContain('Try again in a moment.');
  });

  it('reads the wait from the body when the header is missing', async () => {
    route({
      [STATUS_URL]: [jsonResponse(200, status)],
      [SCAN_URL]: [jsonResponse(429, {detail: 'Too many requests.', retry_after: 3})],
    });
    await openConsole();

    await scan('T1');

    expect(text('[data-scan-result]')).toContain('Try again in 3 seconds.');
  });

  it('keeps the other outcomes as they were', async () => {
    route({
      [STATUS_URL]: [jsonResponse(200, status)],
      [SCAN_URL]: [jsonResponse(404, {status: 'not_found', detail: 'No ticket.'}), jsonResponse(400, {detail: 'Bad.'})],
    });
    await openConsole();

    await scan('T9');
    expect(text('[data-scan-result] strong')).toBe('Not found');
    await scan('T8');
    expect(text('[data-scan-result] strong')).toBe('Unable to check in');
  });

  it('shows "Busy — retry" when an undo is refused', async () => {
    const withRecent = {...status, recent_scans: [{id: 'r1', scanned_at: null, attendee: {name: 'Ada', ticket_code: 'T1'}}]};
    route({[STATUS_URL]: [jsonResponse(200, withRecent)], [UNDO_URL]: [refused('2')]});
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    await openConsole();

    document.querySelector<HTMLButtonElement>('[data-undo-record="r1"]')!.click();
    await flush(20);

    expect(text('[data-scan-result] strong')).toBe('Busy — retry');
    expect(text('[data-scan-result]')).toContain('Try again in 2 seconds.');
  });
});

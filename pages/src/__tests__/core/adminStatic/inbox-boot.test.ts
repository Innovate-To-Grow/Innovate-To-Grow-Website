// mail/inbox/js/inbox-boot.js: the page's wiring. The first list loads with the remembered folder, account and page
// size; a folder switch is served from the cache (no refresh=1); Ctrl/Cmd/Shift/middle click opens a row the
// browser's way; the auto-refresh skips a reply in progress. Keyboard shortcuts: core/admin/inbox-keys-static.test.ts.
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';

import {flush} from '@/__tests__/core/adminStatic';
import {
  htmlResponse,
  type InboxApi,
  listFragment,
  loadInbox,
  mountInbox,
  olderFragment,
  previewFragment,
  query,
  row,
  stubFetch,
} from '@/__tests__/core/adminStatic/inbox';

let ns: InboxApi;
let firstLoad: string;

const answer = (url: string) => {
  if (url.includes('/reply/')) return htmlResponse('<form data-inbox-reply-form data-action="/r/"><textarea name="reply_body"></textarea></form>');
  if (url.includes('older=1')) return htmlResponse(olderFragment([row('9')]));
  if (url.includes('/fragment/?folder=')) return htmlResponse(previewFragment());
  return htmlResponse(listFragment([row('1'), row('2', {unread: true}), row('3')]));
};

const click = (el: Element | null, init: MouseEventInit = {}) => {
  const event = new MouseEvent('click', {bubbles: true, cancelable: true, button: 0, ...init});
  el?.dispatchEvent(event);
  return event;
};
const urls = (mock: ReturnType<typeof stubFetch>) => mock.mock.calls.map(([url]) => String(url));

async function mounted() {
  const root = mountInbox(listFragment([row('1'), row('2', {unread: true}), row('3')]));
  const fetchMock = stubFetch(answer);
  return {root, fetchMock};
}

beforeAll(async () => {
  localStorage.setItem('i2g-inbox-folder', 'SENT');
  localStorage.setItem('i2g-inbox-limit', '50');
  mountInbox('<div id="inbox-loading-skeleton"></div>');
  const fetchMock = stubFetch(answer);
  ns = loadInbox();
  await flush();
  firstLoad = String(fetchMock.mock.calls[0][0]);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  ns.filterState.query = '';
  ns.filterState.unreadOnly = false;
  document.body.innerHTML = '';
});

describe('inbox-boot.js first load and toolbar', () => {
  it('loads the remembered folder, account and page size', () => {
    expect(query(firstLoad)).toEqual({folder: 'SENT', account: 'all', limit: '50'});
  });

  it('switches folders from the cache, dropping the open message', async () => {
    const {root, fetchMock} = await mounted();
    history.replaceState(null, '', '#msg=imap%3A7%7C1');

    click(root.querySelector('[data-inbox-folder="SENT"]'));
    click(root.querySelector('[data-inbox-folder="INBOX"]'));  // and straight back: the tab changed at once
    await flush();

    expect(query(urls(fetchMock)[0])).toEqual({limit: '30', folder: 'SENT', account: 'all'});
    expect(localStorage.getItem('i2g-inbox-folder')).toBe('INBOX');
    expect(location.hash).toBe('');
  });

  it('refreshes every account on Refresh, and pages and accounts on change', async () => {
    const {root, fetchMock} = await mounted();
    click(root.querySelector('[data-inbox-refresh]'));
    await flush();
    expect(query(urls(fetchMock)[0]).refresh).toBe('1');

    const limit = root.querySelector('[data-inbox-limit]') as HTMLSelectElement;
    limit.value = '100';
    limit.dispatchEvent(new Event('change', {bubbles: true}));
    expect(localStorage.getItem('i2g-inbox-limit')).toBe('100');
    const account = root.querySelector('[data-inbox-account]') as HTMLSelectElement;
    account.value = 'imap:7';
    account.dispatchEvent(new Event('change', {bubbles: true}));
    expect(localStorage.getItem('i2g-inbox-account')).toBe('imap:7');
    await flush();
    expect(query(urls(fetchMock).at(-1) as string)).toEqual({limit: '100', folder: 'INBOX', account: 'imap:7'});
    document.body.dispatchEvent(new Event('change', {bubbles: true}));
  });

  it('toggles and remembers the details panel and the list', async () => {
    const {root} = await mounted();
    click(root.querySelector('[data-inbox-account-toggle]'));
    expect(localStorage.getItem('i2g-inbox-account-collapsed')).toBe('0');
    click(root.querySelector('[data-inbox-list-toggle]'));
    expect(localStorage.getItem('i2g-inbox-list-collapsed')).toBe('1');
    expect(root.querySelector('.i2g-mail-shell')?.classList.contains('is-list-collapsed')).toBe(true);
  });

  it('wires Load older, Unread only, the filter box and Retry', async () => {
    const {root, fetchMock} = await mounted();
    click(root.querySelector('[data-inbox-older]'));
    await flush();
    expect(query(urls(fetchMock)[0]).older).toBe('1');

    click(root.querySelector('[data-inbox-unread-only]'));
    expect(ns.filterState.unreadOnly).toBe(true);
    const input = root.querySelector('[data-inbox-filter]') as HTMLInputElement;
    input.value = 'subject 2';
    input.dispatchEvent(new Event('input', {bubbles: true}));
    expect(ns.filterState.query).toBe('subject 2');

    ns.setActiveRow(root, 'imap:7|1');
    (root.querySelector('#inbox-preview-content') as HTMLElement).replaceChildren(ns.errorBox('failed'));
    click(root.querySelector('[data-inbox-retry]'));
    await flush();
    expect(urls(fetchMock).at(-1)).toContain('/admin/mail/inbox/1/fragment/');
  });
});

describe('inbox-boot.js rows and reply', () => {
  it('opens a row in the preview, but leaves modified clicks to the browser', async () => {
    const {root, fetchMock} = await mounted();
    const target = root.querySelector('[data-uid="imap:7|2"] [data-inbox-row-subject]');
    for (const init of [{ctrlKey: true}, {metaKey: true}, {shiftKey: true}, {button: 1}]) {
      expect(click(target, init).defaultPrevented).toBe(false);
    }
    expect(fetchMock).not.toHaveBeenCalled();

    expect(click(target).defaultPrevented).toBe(true);
    await flush();
    expect(urls(fetchMock)).toEqual(['/admin/mail/inbox/2/fragment/?folder=INBOX&account=imap%3A7']);
    expect(root.querySelector('[data-uid="imap:7|2"]')?.classList.contains('is-unread')).toBe(false);
  });

  it('replies, toggles Cc, cancels and submits from the preview', async () => {
    const {root, fetchMock} = await mounted();
    const preview = root.querySelector('#inbox-preview-content') as HTMLElement;
    preview.innerHTML = previewFragment();
    (document.getElementById('inbox-reply-area') as HTMLElement).scrollIntoView = vi.fn();

    click(root.querySelector('[data-inbox-reply-link]'));
    await vi.waitFor(() => expect(root.querySelector('[data-inbox-reply-form]')).not.toBeNull());
    (root.querySelector('[data-inbox-reply-form]') as HTMLFormElement).dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
    expect(urls(fetchMock).at(-1)).toBe('/r/');

    preview.insertAdjacentHTML('beforeend', '<button data-toggle-cc>Cc</button><div data-cc-row style="display:none"><input></div><button data-inbox-cancel-reply>x</button>');
    click(preview.querySelector('[data-toggle-cc]'));
    expect((preview.querySelector('[data-cc-row]') as HTMLElement).style.display).toBe('flex');
    click(preview.querySelector('[data-inbox-cancel-reply]'));
    expect(document.getElementById('inbox-reply-area')?.innerHTML).toBe('');
    document.body.dispatchEvent(new Event('submit', {bubbles: true}));
  });
});

describe('inbox-boot.js auto-refresh', () => {
  it('reloads quietly once the interval has passed, but never over a reply being written', async () => {
    const {root, fetchMock} = await mounted();
    const now = vi.spyOn(Date, 'now');
    now.mockReturnValue(Date.now() + 61_000);
    expect(ns.autoRefreshTick()).toBe(true);
    expect(ns.autoRefreshTick()).toBe(false);  // not again so soon
    now.mockReturnValue(Date.now() + 200_000);
    (document.getElementById('inbox-preview-content') as HTMLElement).innerHTML = '<div id="inbox-reply-area"><form></form></div>';
    expect(ns.autoRefreshTick()).toBe(false);
    (document.getElementById('inbox-reply-area') as HTMLElement).innerHTML = '';
    root.querySelector('[data-inbox-older]')?.setAttribute('disabled', '');
    expect(ns.autoRefreshTick()).toBe(false);
    root.querySelector('.i2g-mail-shell')?.setAttribute('data-inbox-auto-refresh', '0');
    expect(ns.autoRefreshTick()).toBe(false);
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    window.dispatchEvent(new Event('resize'));
    window.dispatchEvent(new Event('beforeunload'));
  });
});

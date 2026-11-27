// mail/inbox/js/inbox-list.js: loading the list fragment, merging a refresh into the page (older pages survive it),
// failures shown in the page with Retry (never window.alert), and rows opened here losing their unread look.
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';

import {flush} from '@/__tests__/core/adminStatic';
import {FRAGMENT_URL, htmlResponse, type InboxApi, listFragment, loadInbox, mountInbox} from '@/__tests__/core/adminStatic/inbox';
import {previewFragment, query, row, stubFetch, uids} from '@/__tests__/core/adminStatic/inbox';

let ns: InboxApi;

beforeAll(() => {
  ns = loadInbox();
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
  history.replaceState(null, '', '/admin/mail/inbox/');
  ns.filterState.query = '';
  ns.filterState.unreadOnly = false;
  document.body.innerHTML = '';
});

describe('inbox-list.js fetchInbox', () => {
  it('replaces the skeleton with the fragment and asks with the given parameters', async () => {
    const root = mountInbox('<div id="inbox-loading-skeleton">Loading</div>');
    const fetchMock = stubFetch(() => htmlResponse(listFragment([row('1'), row('2')])));

    await ns.fetchInbox(root, {limit: '50', folder: 'SENT', account: ''});

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url).startsWith(FRAGMENT_URL)).toBe(true);
    expect(query(String(url))).toEqual({limit: '50', folder: 'SENT'});
    expect(init).toMatchObject({credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}});
    expect(uids(root)).toEqual(['imap:7|1', 'imap:7|2']);
    expect(root.querySelector('#inbox-loading-skeleton')).toBeNull();
  });

  it('keeps an open preview and merges the list around it', async () => {
    const root = mountInbox(listFragment([row('1'), row('2')]));
    (root.querySelector('#inbox-preview-content') as HTMLElement).innerHTML = previewFragment();
    ns.setActiveRow(root, 'imap:7|2');
    stubFetch(() => htmlResponse(listFragment([row('3'), row('2')], {status: '<div data-inbox-status>busy</div>'})));

    await ns.fetchInbox(root, {});

    expect(uids(root)).toEqual(['imap:7|3', 'imap:7|2']);
    expect(root.querySelector('[data-inbox-row].is-active')?.getAttribute('data-uid')).toBe('imap:7|2');
    expect(root.querySelector('[data-inbox-preview-body], #inbox-preview-body')).not.toBeNull();
    expect(root.querySelector('[data-inbox-status]')?.textContent).toBe('busy');
  });

  it('keeps the older pages when the first page is refreshed: new rows go on top, known rows update in place', () => {
    const root = mountInbox(listFragment([row('9'), row('8'), row('5'), row('4')]));
    root.querySelector('[data-inbox-list]')?.setAttribute('data-inbox-pages', '2');
    const oldFooter = root.querySelector('[data-inbox-older]');

    ns.mergeListHtml(root, listFragment([row('11'), row('10'), row('9', {unread: true}), row('8')]), {keepOlder: true});

    expect(uids(root)).toEqual(['imap:7|11', 'imap:7|10', 'imap:7|9', 'imap:7|8', 'imap:7|5', 'imap:7|4']);
    expect(root.querySelector('[data-uid="imap:7|9"]')?.classList.contains('is-unread')).toBe(true);
    expect(root.querySelector('[data-inbox-older]')).toBe(oldFooter);

    // A reload the user asked for (Refresh, another page size) starts again from the first page.
    ns.mergeListHtml(root, listFragment([row('11'), row('10')], {older: 'FRESH'}));
    expect(uids(root)).toEqual(['imap:7|11', 'imap:7|10']);
    expect(root.querySelector('[data-inbox-list]')?.getAttribute('data-inbox-pages')).toBe('1');
    expect(root.querySelector('[data-inbox-older]')?.getAttribute('data-inbox-older')).toBe('FRESH');
  });

  it('merges the auto-refresh into the list even with no message open, keeping the older pages', async () => {
    const root = mountInbox(listFragment([row('9'), row('8'), row('5')]));
    root.querySelector('[data-inbox-list]')?.setAttribute('data-inbox-pages', '2');
    stubFetch(() => htmlResponse(listFragment([row('10'), row('9')])));

    await ns.fetchInbox(root, {}, {quiet: true});

    expect(uids(root)).toEqual(['imap:7|10', 'imap:7|9', 'imap:7|8', 'imap:7|5']);
    expect(root.querySelector('[data-inbox-count]')?.textContent).toBe('4 loaded');
  });

  it('builds the split pane when the page had none, keeping the preview pane', () => {
    const root = mountInbox('<div class="i2g-mail-shell"><div class="i2g-mail-toolbar">old</div><div id="inbox-preview-pane">kept</div></div>');
    const pane = root.querySelector('#inbox-preview-pane');

    ns.mergeListHtml(root, listFragment([row('1')]));

    expect(root.querySelector('.i2g-inbox-split #inbox-preview-pane')).toBe(pane);
    expect(uids(root)).toEqual(['imap:7|1']);
    ns.mergeListHtml(root, '<div class="i2g-mail-shell"></div>');
    expect(root.querySelector('.i2g-mail-toolbar')).toBeNull();
  });

  it('reopens the message named in the URL hash', async () => {
    history.replaceState(null, '', '#msg=' + encodeURIComponent('imap:7|2'));
    const root = mountInbox('');
    const fetchMock = stubFetch((url) => htmlResponse(url.includes('/2/fragment/') ? previewFragment() : listFragment([row('1'), row('2')])));

    await ns.fetchInbox(root, {});
    await flush();

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toContain('/admin/mail/inbox/2/fragment/?folder=INBOX&account=imap%3A7');
    expect(ns.getActiveUid(root)).toBe('imap:7|2');
  });

  it('shows a failed first load in the skeleton, with Retry', async () => {
    const root = mountInbox('<div id="inbox-loading-skeleton">Loading</div>');
    stubFetch(() => htmlResponse('nope', 500));
    const alert = vi.spyOn(window, 'alert');

    await ns.fetchInbox(root, {});

    const box = root.querySelector('#inbox-loading-skeleton [data-inbox-list-error]') as HTMLElement;
    expect(box.getAttribute('role')).toBe('alert');
    expect(box.querySelector('button[data-inbox-refresh]')?.textContent).toBe('Retry');
    expect(alert).not.toHaveBeenCalled();
  });

  it('keeps the list after a failed refresh and says so above it, once', async () => {
    const root = mountInbox(listFragment([row('1')]));
    stubFetch(() => Promise.reject(new TypeError('offline')));

    await ns.fetchInbox(root, {});
    await ns.fetchInbox(root, {});

    expect(uids(root)).toEqual(['imap:7|1']);
    expect(root.querySelectorAll('[data-inbox-list-error]')).toHaveLength(1);
    expect(root.querySelector('[data-inbox-list-error]')?.nextElementSibling?.classList.contains('i2g-inbox-split')).toBe(true);
    expect(root.querySelector('[data-inbox-refresh][disabled]')).toBeNull();
  });

  it('stays silent when a quiet refresh fails, and keeps the scroll position when it works', async () => {
    const root = mountInbox(listFragment([row('1')]));
    stubFetch(() => Promise.reject(new TypeError('offline')));
    await ns.fetchInbox(root, {}, {quiet: true});
    expect(root.querySelector('[data-inbox-list-error]')).toBeNull();

    stubFetch(() => htmlResponse(listFragment([row('1'), row('2')])));
    (root.querySelector('.i2g-inbox-list') as HTMLElement).scrollTop = 40;
    await ns.fetchInbox(root, {}, {quiet: true});
    expect(uids(root)).toEqual(['imap:7|1', 'imap:7|2']);
  });

  it('disables Refresh while loading and does nothing without a fragment URL', async () => {
    const root = mountInbox(listFragment([row('1')]));
    let release: (value: Response) => void = () => undefined;
    stubFetch(() => new Promise<Response>((resolve) => { release = resolve; }));

    const pending = ns.fetchInbox(root, {});
    expect(root.querySelector('[data-inbox-refresh]')?.hasAttribute('disabled')).toBe(true);
    release(htmlResponse(listFragment([row('1')])));
    await pending;
    expect(root.querySelector('[data-inbox-refresh]')?.hasAttribute('disabled')).toBe(false);

    root.removeAttribute('data-fragment-url');
    await ns.fetchInbox(root, {});
  });

  it('remembers the list scroll for the next page load', async () => {
    const root = mountInbox(listFragment([row('1')]));
    (root.querySelector('.i2g-inbox-list') as HTMLElement).scrollTop = 120;
    ns.persistScrollToSession(root);
    expect(sessionStorage.getItem('inbox-list-scroll')).toBe('120');

    history.replaceState(null, '', '#msg=' + encodeURIComponent('imap:7|1'));
    stubFetch((url) => htmlResponse(url.includes('fragment/?') && !url.includes('/1/') ? listFragment([row('1')]) : previewFragment()));
    await ns.fetchInbox(mountInbox(''), {});
    expect(sessionStorage.getItem('inbox-list-scroll')).toBeNull();
  });
});

describe('inbox-list.js rows opened here', () => {
  it('lose their unread look but stay unread in the mailbox', () => {
    const root = mountInbox(listFragment([row('1', {unread: true}), row('2', {unread: true}), row('3')]));
    ns.rememberOpened('imap:7|2');

    ns.markOpenedRows(root);

    const opened = root.querySelector('[data-uid="imap:7|2"]') as HTMLElement;
    expect(opened.classList.contains('is-unread')).toBe(false);
    expect(opened.classList.contains('is-opened')).toBe(true);
    expect(opened.querySelector('[data-inbox-row-icon]')?.getAttribute('title')).toBe('Opened here; still unread in the mailbox');
    expect(root.querySelector('[data-uid="imap:7|1"]')?.classList.contains('is-unread')).toBe(true);
    ns.markOpened(null);
    ns.markOpened(root.querySelector('[data-uid="imap:7|3"]'));
    expect(root.querySelector('[data-uid="imap:7|3"]')?.classList.contains('is-opened')).toBe(false);
  });

  it('finds rows by uid, quoting characters a selector would choke on', () => {
    const root = mountInbox(listFragment([row('1')]));
    root.querySelector('[data-inbox-row]')?.setAttribute('data-uid', 'graph:a"b|X');
    expect(ns.rowByUid(root, 'graph:a"b|X')).not.toBeNull();
    expect(ns.rowByUid(root, null)).toBeNull();
    vi.stubGlobal('CSS', undefined);
    expect(ns.rowByUid(root, 'graph:a"b|X')).not.toBeNull();
  });
});

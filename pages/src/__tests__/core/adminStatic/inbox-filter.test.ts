// mail/inbox/js/inbox-filter.js: the quick filter (sender, subject, snippet) and "Unread only" over the loaded rows,
// and "Load older", which appends the next page with the cursor the server put on the button.
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';

import {
  footer,
  htmlResponse,
  type InboxApi,
  listFragment,
  loadInbox,
  mountInbox,
  olderFragment,
  query,
  row,
  stubFetch,
  uids,
} from '@/__tests__/core/adminStatic/inbox';

let ns: InboxApi;

const ROWS = [
  row('1', {sender: 'Ada Lovelace', subject: 'Engine notes', snippet: 'Analytical', unread: true}),
  row('2', {sender: 'Grace Hopper', subject: 'Compiler', snippet: 'COBOL draft'}),
  row('3', {sender: 'Alan Turing', subject: 'Re: Engine notes', snippet: 'Morphogenesis', unread: true}),
];

const shown = (root: Element) => ns.visibleRows(root).map((el) => el.getAttribute('data-uid'));
const count = (root: Element) => root.querySelector('[data-inbox-count]')?.textContent;
const olderButton = (root: Element) => root.querySelector('[data-inbox-older]') as HTMLButtonElement;

beforeAll(() => {
  ns = loadInbox();
});

afterEach(() => {
  vi.unstubAllGlobals();
  ns.filterState.query = '';
  ns.filterState.unreadOnly = false;
  document.body.innerHTML = '';
});

describe('inbox-filter.js quick filter', () => {
  it('matches every word against sender, subject and snippet, case-insensitively', () => {
    const root = mountInbox(listFragment(ROWS));

    ns.setFilterQuery(root, '  engine   NOTES ');
    expect(shown(root)).toEqual(['imap:7|1', 'imap:7|3']);
    expect(count(root)).toBe('2 of 3 loaded');

    ns.setFilterQuery(root, 'cobol');
    expect(shown(root)).toEqual(['imap:7|2']);
    ns.setFilterQuery(root, 'hopper engine');
    expect(shown(root)).toEqual([]);
    expect((root.querySelector('[data-inbox-filter-empty]') as HTMLElement).hidden).toBe(false);

    ns.setFilterQuery(root, '');
    expect(shown(root)).toHaveLength(3);
    expect(count(root)).toBe('3 loaded');
    expect((root.querySelector('[data-inbox-filter-empty]') as HTMLElement).hidden).toBe(true);
  });

  it('does not search the date or the account line', () => {
    const root = mountInbox(listFragment(ROWS));
    ns.setFilterQuery(root, '2026-10-01');
    expect(shown(root)).toEqual([]);
    const bare = document.createElement('a');
    bare.textContent = ' Whole  Row ';
    expect(ns.rowText(bare)).toBe('whole row');
  });

  it('shows unread rows only, combined with the text filter', () => {
    const root = mountInbox(listFragment(ROWS));

    ns.toggleUnreadOnly(root);
    expect(shown(root)).toEqual(['imap:7|1', 'imap:7|3']);
    expect(root.querySelector('[data-inbox-unread-only]')?.getAttribute('aria-pressed')).toBe('true');
    ns.setFilterQuery(root, 'turing');
    expect(shown(root)).toEqual(['imap:7|3']);
    ns.toggleUnreadOnly(root, false);
    expect(shown(root)).toEqual(['imap:7|3']);
    expect(root.querySelector('[data-inbox-unread-only]')?.getAttribute('aria-pressed')).toBe('false');
  });

  it('is applied again to a list rendered afresh, input included', () => {
    const root = mountInbox(listFragment(ROWS));
    ns.setFilterQuery(root, 'grace');
    root.innerHTML = listFragment(ROWS);

    ns.applyFilter(root);

    expect(shown(root)).toEqual(['imap:7|2']);
    expect((root.querySelector('[data-inbox-filter]') as HTMLInputElement).value).toBe('grace');
    ns.applyFilter(null);
  });
});

describe('inbox-filter.js Load older', () => {
  it('appends the next page, skips rows already listed and takes the new footer', async () => {
    const root = mountInbox(listFragment(ROWS, {limit: '15'}));
    const fetchMock = stubFetch(() => htmlResponse(olderFragment([row('3'), row('4'), row('5', {unread: true})], 'CURSOR2')));

    await ns.loadOlder(root, olderButton(root));

    expect(query(String(fetchMock.mock.calls[0][0]))).toEqual({
      limit: '15', folder: 'INBOX', account: 'all', older: '1', cursor: 'CURSOR1',
    });
    expect(uids(root)).toEqual(['imap:7|1', 'imap:7|2', 'imap:7|3', 'imap:7|4', 'imap:7|5']);
    expect(olderButton(root).getAttribute('data-inbox-older')).toBe('CURSOR2');
    expect(root.querySelector('[data-inbox-list]')?.lastElementChild?.hasAttribute('data-inbox-list-footer')).toBe(true);
    expect(root.querySelector('[data-inbox-list]')?.getAttribute('data-inbox-pages')).toBe('2');
    expect(count(root)).toBe('5 loaded');
  });

  it('filters the appended rows too, and ends with "No older messages"', async () => {
    const root = mountInbox(listFragment(ROWS));
    ns.toggleUnreadOnly(root, true);
    ns.rememberOpened('imap:7|5');
    stubFetch(() => htmlResponse(olderFragment([row('4'), row('5', {unread: true}), row('6', {unread: true})])));

    await ns.loadOlder(root, olderButton(root));

    expect(shown(root)).toEqual(['imap:7|1', 'imap:7|3', 'imap:7|6']);
    expect(root.querySelector('[data-inbox-older]')).toBeNull();
    expect(root.querySelector('[data-inbox-list-footer]')?.textContent).toContain('No older messages.');
    sessionStorage.clear();
  });

  it('keeps the button as Retry, with a note, when the page fails', async () => {
    const root = mountInbox(listFragment(ROWS));
    stubFetch(() => htmlResponse('down', 502));

    await ns.loadOlder(root, olderButton(root));
    await ns.loadOlder(root, olderButton(root));

    expect(olderButton(root).disabled).toBe(false);
    expect(olderButton(root).textContent).toBe('Retry');
    expect(root.querySelectorAll('[data-inbox-older-error]')).toHaveLength(1);
    expect(uids(root)).toHaveLength(3);
  });

  it('ignores a click while a page is loading, and pages without a footer or URL', async () => {
    const root = mountInbox(listFragment(ROWS));
    const fetchMock = stubFetch(() => htmlResponse(olderFragment([row('9')])));
    olderButton(root).disabled = true;
    await ns.loadOlder(root, olderButton(root));
    expect(fetchMock).not.toHaveBeenCalled();

    olderButton(root).disabled = false;
    root.querySelector('[data-inbox-list-footer]')?.remove();
    const loose = document.createElement('button');
    loose.setAttribute('data-inbox-older', 'C');
    await ns.loadOlder(root, loose);
    expect(uids(root).at(-1)).toBe('imap:7|9');
    expect(root.querySelector('[data-inbox-list]')?.lastElementChild?.hasAttribute('data-inbox-list-footer')).toBe(true);

    stubFetch(() => htmlResponse('<div data-inbox-older-page></div>'));
    await ns.loadOlder(root, olderButton(root) ?? loose);
    root.removeAttribute('data-fragment-url');
    await ns.loadOlder(root, loose);
    expect(footer(null)).toContain('No older messages.');
  });
});

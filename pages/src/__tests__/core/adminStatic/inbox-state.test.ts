// mail/inbox/js/inbox-state.js: what the inbox remembers (folder, account, page size, the collapsed panels, the rows
// opened in this tab) and the shell's layout state. The details panel starts collapsed.
import {afterEach, beforeAll, describe, expect, it} from 'vitest';

import {type InboxApi, listFragment, loadInbox, mountInbox, row} from '@/__tests__/core/adminStatic/inbox';

let ns: InboxApi;

beforeAll(() => {
  ns = loadInbox();
});

afterEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  document.body.innerHTML = '';
});

describe('inbox-state.js storage', () => {
  it('builds query strings from the non-empty parameters only', () => {
    expect(ns.buildUrl('/f/', {limit: '30', folder: '', account: 'imap:7'})).toBe('/f/?limit=30&account=imap%3A7');
    expect(ns.buildUrl('/f/?a=1', {b: 'x y'})).toBe('/f/?a=1&b=x%20y');
    expect(ns.buildUrl('/f/', {})).toBe('/f/');
  });

  it('remembers the folder, the account and the page size, with safe defaults', () => {
    expect([ns.storedFolder(), ns.storedAccount(), ns.storedLimit()]).toEqual(['INBOX', 'all', '']);
    ns.storeFolder('SENT');
    ns.storeAccount('imap:7');
    ns.storeLimit('50');
    expect([ns.storedFolder(), ns.storedAccount(), ns.storedLimit()]).toEqual(['SENT', 'imap:7', '50']);
    ns.storeFolder('Archive');
    ns.storeAccount('');
    ns.storeLimit('lots');
    expect([ns.storedFolder(), ns.storedAccount(), ns.storedLimit()]).toEqual(['INBOX', 'all', '50']);
    localStorage.setItem('i2g-inbox-limit', '1e9');
    expect(ns.storedLimit()).toBe('');
  });

  it('keeps the details panel collapsed until the user opens it', () => {
    expect(ns.storedAccountCollapsed()).toBe(true);
    ns.storeAccountCollapsed(false);
    expect(ns.storedAccountCollapsed()).toBe(false);
    expect(ns.storedListCollapsed()).toBe(false);
    ns.storeListCollapsed(true);
    expect(ns.storedListCollapsed()).toBe(true);
  });

  it('remembers the rows opened in this tab, newest last and capped', () => {
    ns.rememberOpened('imap:7|1');
    ns.rememberOpened('imap:7|2');
    ns.rememberOpened('imap:7|1');
    ns.rememberOpened('');
    expect(ns.openedUids()).toEqual(['imap:7|2', 'imap:7|1']);
    for (let index = 0; index < 600; index += 1) ns.rememberOpened(`graph:x|${index}`);
    expect(ns.openedUids()).toHaveLength(500);
    expect(ns.openedUids().at(-1)).toBe('graph:x|599');
    sessionStorage.setItem('i2g-inbox-opened', '{"not": "a list"}');
    expect(ns.openedUids()).toEqual([]);
    sessionStorage.setItem('i2g-inbox-opened', 'not json');
    expect(ns.openedUids()).toEqual([]);
  });

  it('falls back when storage is unavailable', () => {
    const original = Object.getOwnPropertyDescriptor(window, 'localStorage');
    Object.defineProperty(window, 'localStorage', {configurable: true, get: () => { throw new Error('denied'); }});
    try {
      ns.storeFolder('SENT');
      expect([ns.storedFolder(), ns.storedAccount(), ns.storedAccountCollapsed()]).toEqual(['INBOX', 'all', true]);
    } finally {
      if (original) Object.defineProperty(window, 'localStorage', original);
    }
  });
});

describe('inbox-state.js page state', () => {
  it('reads the folder, account and limit from the page, else from storage', () => {
    const root = mountInbox(listFragment([row('1')], {folder: 'SENT', limit: '50'}));
    expect([ns.getFolder(root), ns.getAccount(root), ns.getLimit(root)]).toEqual(['SENT', 'all', '50']);
    expect(ns.listParams(root, {refresh: '1'})).toEqual({limit: '50', folder: 'SENT', account: 'all', refresh: '1'});

    localStorage.setItem('i2g-inbox-limit', '15');
    const empty = mountInbox('');
    expect([ns.getFolder(empty), ns.getAccount(empty), ns.getLimit(empty)]).toEqual(['INBOX', 'all', '15']);
    expect([ns.getFolder(null), ns.getAccount(null), ns.getLimit(null)]).toEqual(['INBOX', 'all', '15']);
  });

  it('switches the active folder tab', () => {
    const root = mountInbox(listFragment([row('1')]));
    ns.setActiveFolderTab(root, 'SENT');
    const sent = root.querySelector('[data-inbox-folder="SENT"]') as HTMLElement;
    expect(sent.classList.contains('i2g-mail-folder-tab--active')).toBe(true);
    expect(sent.getAttribute('aria-selected')).toBe('true');
    expect(ns.getFolder(root)).toBe('SENT');
    ns.setActiveFolderTab(null, 'INBOX');
  });

  it('applies the remembered panel states to the shell', () => {
    const root = mountInbox(listFragment([row('1')]));
    const shell = root.querySelector('.i2g-mail-shell') as HTMLElement;

    ns.applyLayoutState(root);
    expect(shell.classList.contains('is-account-collapsed')).toBe(true);
    expect(root.querySelector('[data-inbox-account-toggle-label]')?.textContent).toBe('Show details');

    ns.storeAccountCollapsed(false);
    ns.storeListCollapsed(true);
    ns.applyLayoutState(root);
    expect(shell.classList.contains('is-account-collapsed')).toBe(false);
    expect(root.querySelector('[data-inbox-account-toggle]')?.getAttribute('aria-expanded')).toBe('true');
    expect(root.querySelector('[data-inbox-account-toggle-label]')?.textContent).toBe('Hide details');
    expect(shell.classList.contains('is-list-collapsed')).toBe(true);
    expect(root.querySelector('[data-inbox-list-toggle]')?.getAttribute('title')).toBe('Expand message list');
    expect(root.querySelector('.i2g-inbox-list-toggle__icon')?.textContent).toBe('chevron_right');

    ns.setAccountCollapsed(null, true);
    ns.setListCollapsed(mountInbox(''), true);
  });

  it('knows the open message and whether a preview is shown', () => {
    const root = mountInbox(listFragment([row('1'), row('2')]));
    expect([ns.getActiveUid(root), ns.hasPreviewContent(root)]).toEqual([null, false]);
    root.querySelector('[data-uid="imap:7|2"]')?.classList.add('is-active');
    (root.querySelector('#inbox-preview-content') as HTMLElement).innerHTML = '<h3>Open</h3>';
    expect([ns.getActiveUid(root), ns.hasPreviewContent(root)]).toEqual(['imap:7|2', true]);
    expect(ns.getRoot(root.querySelector('[data-inbox-row]'))).toBe(root);
    expect(ns.getRoot(null)).toBeNull();
    expect(ns.hasPreviewContent(mountInbox(''))).toBe(false);
  });
});

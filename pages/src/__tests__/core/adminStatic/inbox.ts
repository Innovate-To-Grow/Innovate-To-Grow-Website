// Fixtures for the Mail -> Inbox script tests (src/apps/mail/static/mail/inbox/js/*.js): the scripts loaded in the
// page's order, and fragments shaped like the server's (admin/mail/inbox/detail/_inbox_full_body.html and friends).
import {vi} from 'vitest';

import {readRepoFile} from '@/__tests__/core/adminStatic';

export const INBOX_SCRIPTS = ['state', 'list', 'filter', 'preview', 'reply', 'keys', 'boot'].map(
  (name) => `src/apps/mail/static/mail/inbox/js/inbox-${name}.js`,
);
export const FRAGMENT_URL = '/admin/mail/inbox/fragment/';

type Root = Element | null;
type Params = Record<string, string>;
export interface FilterState {
  query: string;
  unreadOnly: boolean;
}

export interface InboxApi {
  filterState: FilterState;
  buildUrl(base: string, params: Params): string;
  getRoot(el: Root): HTMLElement | null;
  storedFolder(): string;
  storeFolder(folder: string): void;
  storedAccount(): string;
  storeAccount(account: string): void;
  storedLimit(): string;
  storeLimit(limit: string): void;
  storedAccountCollapsed(): boolean;
  storeAccountCollapsed(collapsed: boolean): void;
  storedListCollapsed(): boolean;
  storeListCollapsed(collapsed: boolean): void;
  openedUids(): string[];
  rememberOpened(uid: string): void;
  getAccount(root: Root): string;
  getFolder(root: Root): string;
  getLimit(root: Root): string;
  listParams(root: Element, extra?: Params): Params;
  setActiveFolderTab(root: Root, folder: string): void;
  setAccountCollapsed(root: Root, collapsed: boolean): void;
  setListCollapsed(root: Root, collapsed: boolean): void;
  applyLayoutState(root: Element): void;
  getActiveUid(root: Element): string | null;
  hasPreviewContent(root: Element): boolean;
  fragmentText(response: Response): Promise<string>;
  mergeListHtml(root: Element, html: string, options?: {keepOlder?: boolean}): void;
  persistScrollToSession(root: Element): void;
  showListError(root: Element, message: string): void;
  errorBox(message: string, retryAttribute?: string): HTMLElement;
  fetchInbox(root: Element, params?: Params, options?: {quiet?: boolean}): Promise<void>;
  rowByUid(root: Element, uid: string | null): HTMLElement | null;
  setActiveRow(root: Element, uid: string | null): void;
  markOpened(row: Element | null): void;
  markOpenedRows(root: Element): void;
  rowText(row: Element): string;
  rowMatches(row: Element, state: FilterState): boolean;
  applyFilter(root: Root): void;
  setFilterQuery(root: Root, query: string): void;
  toggleUnreadOnly(root: Root, value?: boolean): void;
  visibleRows(root: Element): HTMLElement[];
  loadOlder(root: Element, button: HTMLButtonElement): Promise<void>;
  initPreviewIframe(container: Element): void;
  getPreviewIframeSize(iframe: HTMLIFrameElement): {width: number; height: number};
  watchPreviewIframeAssets(iframe: HTMLIFrameElement): void;
  resizePreviewIframe(): void;
  getHashUid(): string | null;
  setHashUid(uid: string | null): void;
  clearPreviewPane(root: Root): void;
  loadPreview(root: Element, row: Element): Promise<void>;
  retryPreview(root: Element): Promise<void>;
  loadReplyForm(area: HTMLElement, url: string): Promise<void>;
  retryReplyForm(area: HTMLElement): Promise<void>;
  showReplySent(area: HTMLElement, message: unknown): void;
  submitReplyForm(form: HTMLFormElement, area: HTMLElement): Promise<void>;
  openReply(root: Element | Document): boolean;
  cancelReply(): boolean;
  toggleCc(toggle: HTMLElement): void;
  stepRow(root: Element, delta: number): HTMLElement | null;
  handleKey(event: KeyboardEvent): boolean;
  autoRefreshTick(): boolean;
}

export const inbox = () => (window as unknown as {I2GInbox: InboxApi}).I2GInbox;

/** Load every inbox script, as list.html does; the auto-refresh interval is not started (tests tick it). */
export function loadInbox() {
  vi.spyOn(window, 'setInterval').mockImplementation(() => 0 as unknown as ReturnType<typeof setInterval>);
  for (const script of INBOX_SCRIPTS) window.eval(readRepoFile(script));
  return inbox();
}

export interface RowOptions {
  unread?: boolean;
  sender?: string;
  subject?: string;
  snippet?: string;
}

export function row(uid: string, {unread = false, sender = 'Pat Lee', subject = `Subject ${uid}`, snippet = 'Body'}: RowOptions = {}) {
  const icon = unread ? 'mark_email_unread' : 'mail';
  return `<a href="/admin/mail/inbox/${uid}/?folder=INBOX&amp;account=imap%3A7" data-inbox-row data-uid="imap:7|${uid}"
      data-preview-url="/admin/mail/inbox/${uid}/fragment/?folder=INBOX&amp;account=imap%3A7"
      class="inbox-list-row${unread ? ' is-unread' : ''}">
    <span data-inbox-row-icon title="${unread ? 'Unread' : 'Read'}">${icon}</span>
    <span data-inbox-row-sender>${sender}</span><span>2026-10-01</span>
    <div data-inbox-row-subject>${subject}</div><div data-inbox-row-snippet>${snippet}</div></a>`;
}

export function footer(older: string | null = 'CURSOR1') {
  return older === null
    ? '<div data-inbox-list-footer><p>No older messages.</p></div>'
    : `<div data-inbox-list-footer><button type="button" data-inbox-older="${older}"><span data-inbox-older-label>Load older</span></button></div>`;
}

export interface ListOptions {
  folder?: 'INBOX' | 'SENT';
  limit?: string;
  older?: string | null;
  autoRefresh?: number;
  status?: string;
}

/** A first-page fragment: toolbar, details panel, list head, filter bar, the rows, their footer and the preview. */
export function listFragment(rows: string[], {folder = 'INBOX', limit = '30', older = 'CURSOR1', autoRefresh = 60, status = ''}: ListOptions = {}) {
  const tab = (name: string) =>
    `<button type="button" data-inbox-folder="${name}" class="i2g-mail-folder-tab${name === folder ? ' i2g-mail-folder-tab--active' : ''}">${name}</button>`;
  const limits = ['15', '30', '50', '100'].map((value) => `<option value="${value}"${value === limit ? ' selected' : ''}>${value}</option>`);
  return `<div class="i2g-mail-shell is-account-collapsed" data-inbox-auto-refresh="${autoRefresh}">
    <div class="i2g-mail-toolbar">${tab('INBOX')}${tab('SENT')}
      <select data-inbox-account><option value="all" selected>All</option><option value="imap:7">imap</option></select>
      <button type="button" data-inbox-refresh>Refresh</button>
      <select data-inbox-limit>${limits.join('')}</select>
      <button type="button" data-inbox-account-toggle aria-expanded="false"><span data-inbox-account-toggle-label>Show details</span></button>
    </div>
    <div data-inbox-account-panel>panel</div>${status}
    <div class="i2g-inbox-split"><div class="i2g-inbox-list-panel">
      <div class="i2g-inbox-list-head"><span data-inbox-count>${rows.length} loaded</span>
        <button type="button" data-inbox-list-toggle><span class="i2g-inbox-list-toggle__icon">chevron_left</span></button></div>
      <div data-inbox-filter-bar><input type="search" data-inbox-filter>
        <button type="button" data-inbox-unread-only aria-pressed="false">Unread only</button></div>
      <p data-inbox-filter-empty hidden>No loaded message matches the filter.</p>
      <div id="inbox-message-list" class="i2g-inbox-list" data-inbox-list data-inbox-pages="1">${rows.join('')}${footer(older)}</div>
    </div>
    <div id="inbox-preview-pane"><div id="inbox-preview-content"><div id="inbox-preview-empty">Select</div></div></div></div>
  </div>`;
}

/** An older page (?older=1): rows and their footer only. */
export const olderFragment = (rows: string[], older: string | null = null) =>
  `<div data-inbox-older-page>${rows.join('')}${footer(older)}</div>`;

/** A preview fragment (_inbox_preview.html), with the body as the page embeds it. */
export function previewFragment(body = '<p>Hello</p>', {sent = false} = {}) {
  const reply = sent ? '' : '<a href="#" data-inbox-reply-link="/admin/mail/inbox/42/reply/fragment/">Reply</a>';
  return `<h3>Subject</h3><div>${reply}<a href="/admin/mail/inbox/42/" data-inbox-full-page>Open full page</a></div>
    <script type="application/json" id="inbox-preview-body-data">${JSON.stringify(body)}</script>
    <div data-inbox-body-scroll><iframe id="inbox-preview-body" data-inbox-body-frame sandbox="allow-popups allow-same-origin"></iframe></div>
    <div id="inbox-reply-area"></div>`;
}

export function mountInbox(fragment = '') {
  document.body.innerHTML = `<div id="inbox-all-dynamic" data-fragment-url="${FRAGMENT_URL}">${fragment}</div>`;
  return document.getElementById('inbox-all-dynamic') as HTMLElement;
}

export const htmlResponse = (body: string, status = 200) =>
  new Response(body, {status, headers: {'Content-Type': 'text/html; charset=utf-8'}});

/** Replace fetch: `answer` gets each URL (and init) and returns the Response (or throws, a network error). */
export function stubFetch(answer: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => answer(String(input), init));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

export const query = (url: string) => Object.fromEntries(new URL(url, 'http://test').searchParams);
export const uids = (root: Element) => [...root.querySelectorAll('[data-inbox-row]')].map((el) => el.getAttribute('data-uid'));

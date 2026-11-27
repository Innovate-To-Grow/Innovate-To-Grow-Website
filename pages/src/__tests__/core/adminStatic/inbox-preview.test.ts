// mail/inbox/js/inbox-preview.js: opening a message in the preview pane (it is never marked read in the mailbox; the
// row only stops looking unread here), its sandboxed body frame sized to the mail (wide mail widens the frame and
// scrolls sideways instead of being cut off), the URL hash, and Retry after a failed load.
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';

import {flush} from '@/__tests__/core/adminStatic';
import {
  htmlResponse,
  type InboxApi,
  listFragment,
  loadInbox,
  mountInbox,
  previewFragment,
  row,
  stubFetch,
} from '@/__tests__/core/adminStatic/inbox';

let ns: InboxApi;

beforeAll(() => {
  ns = loadInbox();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  sessionStorage.clear();
  history.replaceState(null, '', '/admin/mail/inbox/');
  document.body.innerHTML = '';
});

const firstRow = (root: Element) => root.querySelector('[data-inbox-row]') as HTMLElement;
const content = (root: Element) => root.querySelector('#inbox-preview-content') as HTMLElement;

function sizeFrame(iframe: HTMLIFrameElement, {pane, width, height}: {pane: number; width: number; height: number}) {
  const doc = iframe.contentDocument as Document;
  Object.defineProperty(iframe, 'clientWidth', {configurable: true, get: () => pane});
  for (const el of [doc.body, doc.documentElement]) {
    Object.defineProperty(el, 'scrollWidth', {configurable: true, get: () => width});
    Object.defineProperty(el, 'scrollHeight', {configurable: true, get: () => height});
  }
}

describe('inbox-preview.js loadPreview', () => {
  it('opens the message, marks the row active and opened here, and keeps it in the hash', async () => {
    const root = mountInbox(listFragment([row('1', {unread: true}), row('2')]));
    const fetchMock = stubFetch(() => htmlResponse(previewFragment('<p>Hi</p>')));

    const pending = ns.loadPreview(root, firstRow(root));
    expect(root.querySelector('#inbox-preview-pane')?.classList.contains('is-loading')).toBe(true);
    expect(content(root).textContent).toContain('Loading message...');
    await pending;

    expect(String(fetchMock.mock.calls[0][0])).toBe('/admin/mail/inbox/1/fragment/?folder=INBOX&account=imap%3A7');
    expect(ns.getActiveUid(root)).toBe('imap:7|1');
    expect(ns.getHashUid()).toBe('imap:7|1');
    expect(ns.openedUids()).toEqual(['imap:7|1']);
    expect(firstRow(root).classList.contains('is-unread')).toBe(false);
    expect(content(root).querySelector('[data-inbox-full-page]')).not.toBeNull();
    expect(root.querySelector('#inbox-preview-pane')?.classList.contains('is-loading')).toBe(false);
  });

  it('shows a failed load in the pane with Retry, which loads the open message again', async () => {
    const root = mountInbox(listFragment([row('1'), row('2')]));
    stubFetch(() => Promise.reject(new TypeError('offline')));
    await ns.loadPreview(root, firstRow(root));

    const retry = content(root).querySelector('button[data-inbox-retry]') as HTMLElement;
    expect(content(root).querySelector('[role="alert"]')?.textContent).toContain('Could not load the message.');
    expect(retry.textContent).toBe('Retry');

    stubFetch(() => htmlResponse(previewFragment()));
    await ns.retryPreview(root);
    expect(content(root).querySelector('#inbox-preview-body')).not.toBeNull();
    ns.setActiveRow(root, null);
    await ns.retryPreview(root);
  });

  it('does nothing for a row without a preview URL or a page without a pane', async () => {
    const root = mountInbox(listFragment([row('1')]));
    firstRow(root).removeAttribute('data-preview-url');
    const fetchMock = stubFetch(() => htmlResponse(''));
    await ns.loadPreview(root, firstRow(root));
    await ns.loadPreview(mountInbox(''), document.createElement('a'));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('clears the pane back to its empty state', () => {
    const root = mountInbox(listFragment([row('1')]));
    ns.setActiveRow(root, 'imap:7|1');
    content(root).innerHTML = '<h3>Open</h3>';

    ns.clearPreviewPane(root);

    expect(content(root).querySelector('#inbox-preview-empty')).not.toBeNull();
    expect(ns.getActiveUid(root)).toBeNull();
    ns.clearPreviewPane(null);
  });
});

describe('inbox-preview.js hash', () => {
  it('reads, writes and drops the open message', () => {
    ns.setHashUid('graph:a@b.c|AAMk=');
    expect(location.hash).toBe('#msg=graph%3Aa%40b.c%7CAAMk%3D');
    expect(ns.getHashUid()).toBe('graph:a@b.c|AAMk=');
    ns.setHashUid(null);
    expect(location.hash).toBe('');
    expect(ns.getHashUid()).toBeNull();
    history.replaceState(null, '', '#msg=%E0%A4%A');
    expect(ns.getHashUid()).toBeNull();
  });
});

describe('inbox-preview.js body frame', () => {
  it('loads the body into the frame and sizes it once it loads', () => {
    vi.useFakeTimers();
    const root = mountInbox(listFragment([row('1')]));
    content(root).innerHTML = previewFragment('<p>Hello</p>');
    const iframe = root.querySelector('#inbox-preview-body') as HTMLIFrameElement;

    ns.initPreviewIframe(content(root));

    expect(iframe.srcdoc).toBe('<p>Hello</p>');
    iframe.onload?.(new Event('load'));
    vi.advanceTimersByTime(60);
    expect(iframe.style.height).toBe('240px');
    ns.initPreviewIframe(document.createElement('div'));
  });

  it('gives wide mail its own width (the wrapper scrolls sideways) and fits narrow mail to the pane', () => {
    const root = mountInbox(listFragment([row('1')]));
    content(root).innerHTML = previewFragment();
    const iframe = root.querySelector('#inbox-preview-body') as HTMLIFrameElement;

    sizeFrame(iframe, {pane: 590, width: 700, height: 1800});
    ns.resizePreviewIframe();
    expect([iframe.style.width, iframe.style.height]).toEqual(['700px', '1800px']);
    expect(iframe.contentDocument?.documentElement.style.overflow).toBe('hidden');

    sizeFrame(iframe, {pane: 590, width: 590, height: 100});
    ns.resizePreviewIframe();
    expect([iframe.style.width, iframe.style.height]).toEqual(['100%', '240px']);
  });

  it('resizes again as the images in the mail load', () => {
    const root = mountInbox(listFragment([row('1')]));
    content(root).innerHTML = previewFragment();
    const iframe = root.querySelector('#inbox-preview-body') as HTMLIFrameElement;
    const doc = iframe.contentDocument as Document;
    doc.body.innerHTML = '<img src="https://img.example/a.png"><img>';
    const [pending, done] = [...doc.querySelectorAll('img')];
    Object.defineProperty(pending, 'complete', {value: false});
    Object.defineProperty(done, 'complete', {value: true});
    const listen = vi.spyOn(pending, 'addEventListener');

    ns.watchPreviewIframeAssets(iframe);

    expect(listen.mock.calls.map(([type]) => type)).toEqual(['load', 'error']);
  });

  it('copes with a frame it cannot read, and with no frame at all', async () => {
    const iframe = document.createElement('iframe');
    Object.defineProperty(iframe, 'contentDocument', {get: () => { throw new DOMException('blocked'); }});
    expect(ns.getPreviewIframeSize(iframe)).toEqual({width: 0, height: 0});
    ns.watchPreviewIframeAssets(iframe);
    document.body.innerHTML = '';
    ns.resizePreviewIframe();
    await flush();
  });
});

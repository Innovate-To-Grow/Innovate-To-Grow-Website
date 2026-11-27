// mail/inbox/js/inbox-keys.js: keyboard shortcuts, as in Gmail. j / k open the next / previous visible message,
// Enter opens the selected one, r replies, Esc closes the reply and then the message, / goes to the quick filter.
// Keys typed into a field or with Ctrl / Cmd / Alt are left alone. (The other inbox scripts: core/adminStatic/inbox-*.)
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

const key = (keyName: string, target: Element = document.body, init: KeyboardEventInit = {}) => {
  const event = new KeyboardEvent('keydown', {key: keyName, bubbles: true, cancelable: true, ...init});
  target.dispatchEvent(event);
  return event;
};

async function mounted() {
  const root = mountInbox(listFragment([row('1'), row('2', {unread: true}), row('3')]));
  const fetchMock = stubFetch((url) =>
    htmlResponse(url.includes('/reply/') ? '<form data-inbox-reply-form data-action="/r/"></form>' : previewFragment()),
  );
  return {root, fetchMock};
}

beforeAll(() => {
  ns = loadInbox();
});

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  ns.filterState.query = '';
  ns.filterState.unreadOnly = false;
  history.replaceState(null, '', '/admin/mail/inbox/');
  document.body.innerHTML = '';
});

describe('inbox-keys.js shortcuts', () => {
  it('j / k move through the visible rows and open them; Enter opens the selected one', async () => {
    const {root, fetchMock} = await mounted();
    ns.setFilterQuery(root, 'subject');
    (root.querySelector('[data-uid="imap:7|2"]') as HTMLElement).hidden = true;

    expect(key('j').defaultPrevented).toBe(true);
    expect(ns.getActiveUid(root)).toBe('imap:7|1');
    key('j');
    expect(ns.getActiveUid(root)).toBe('imap:7|3');  // the hidden row is skipped
    key('j');
    expect(ns.getActiveUid(root)).toBe('imap:7|3');
    key('k');
    expect(ns.getActiveUid(root)).toBe('imap:7|1');
    (document.activeElement as HTMLElement).blur();
    key('Enter');
    expect(ns.getActiveUid(root)).toBe('imap:7|1');
    await flush();
    expect(fetchMock).toHaveBeenCalled();
    expect(key('Enter', root.querySelector('[data-inbox-refresh]') as Element).defaultPrevented).toBe(false);
  });

  it('k starts from the last row, and an empty list ignores both', async () => {
    const {root} = await mounted();
    key('k');
    expect(ns.getActiveUid(root)).toBe('imap:7|3');
    mountInbox(listFragment([]));
    expect(ns.stepRow(document.getElementById('inbox-all-dynamic') as Element, 1)).toBeNull();
  });

  it('r replies, Esc closes the reply then the message, / goes to the filter', async () => {
    const {root} = await mounted();
    (root.querySelector('#inbox-preview-content') as HTMLElement).innerHTML = previewFragment();
    (document.getElementById('inbox-reply-area') as HTMLElement).scrollIntoView = vi.fn();
    history.replaceState(null, '', '#msg=imap%3A7%7C1');

    expect(key('r').defaultPrevented).toBe(true);
    await vi.waitFor(() => expect(root.querySelector('#inbox-reply-area form')).not.toBeNull());
    expect(key('Escape').defaultPrevented).toBe(true);
    expect(root.querySelector('#inbox-preview-body')).not.toBeNull();
    key('Escape');
    expect(root.querySelector('#inbox-preview-empty')).not.toBeNull();
    expect(location.hash).toBe('');
    expect(key('Escape').defaultPrevented).toBe(false);
    expect(key('r').defaultPrevented).toBe(false);

    key('/');
    const filter = root.querySelector('[data-inbox-filter]') as HTMLInputElement;
    expect(document.activeElement).toBe(filter);
    ns.setFilterQuery(root, 'abc');
    key('Escape', filter);
    expect(ns.filterState.query).toBe('');
  });

  it('leaves typing, modified keys and other keys alone', async () => {
    const {root} = await mounted();
    const filter = root.querySelector('[data-inbox-filter]') as HTMLElement;
    expect(key('j', filter).defaultPrevented).toBe(false);
    expect(key('j', document.body, {ctrlKey: true}).defaultPrevented).toBe(false);
    expect(key('x').defaultPrevented).toBe(false);
    root.querySelector('[data-inbox-filter-bar]')?.remove();
    expect(key('/').defaultPrevented).toBe(false);
    document.body.innerHTML = '';
    expect(key('j').defaultPrevented).toBe(false);
  });
});

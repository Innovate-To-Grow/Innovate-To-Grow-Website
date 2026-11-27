// mail/inbox/js/inbox-reply.js: the inline reply below the preview. The form loads (with Retry when it cannot), is
// sent as form data with the CSRF token, and the server's confirmation is inserted as text, never as HTML.
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';

import {jsonResponse} from '@/__tests__/core/adminStatic';
import {htmlResponse, type InboxApi, loadInbox, mountInbox, previewFragment, stubFetch} from '@/__tests__/core/adminStatic/inbox';

let ns: InboxApi;

const FORM = `<form data-inbox-reply-form data-action="/admin/mail/inbox/42/reply/fragment/">
  <input name="to_email" value="pat@example.com"><button type="button" data-toggle-cc>Cc</button>
  <div data-cc-row style="display:none;"><input name="cc_email"></div>
  <textarea name="reply_body">Thanks</textarea>
  <button type="submit" data-inbox-send-btn>Send Reply</button><div data-inbox-reply-status class="hidden"></div></form>`;

const area = () => document.getElementById('inbox-reply-area') as HTMLElement;
const form = () => area().querySelector('form') as HTMLFormElement;

function mountPreview({sent = false} = {}) {
  const root = mountInbox(`<div id="inbox-preview-content">${previewFragment('<p>x</p>', {sent})}</div>`);
  area().scrollIntoView = vi.fn();
  return root;
}

beforeAll(() => {
  ns = loadInbox();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  document.body.innerHTML = '';
});

describe('inbox-reply.js form', () => {
  it('opens the reply form under the message and focuses the text', async () => {
    const root = mountPreview();
    const fetchMock = stubFetch(() => htmlResponse(FORM));

    expect(ns.openReply(root)).toBe(true);
    await vi.waitFor(() => expect(form()).not.toBeNull());

    expect(String(fetchMock.mock.calls[0][0])).toBe('/admin/mail/inbox/42/reply/fragment/');
    expect((root.querySelector('[data-inbox-reply-link]') as HTMLElement).style.display).toBe('none');
    expect(document.activeElement?.getAttribute('name')).toBe('reply_body');
    expect(ns.openReply(root)).toBe(false);  // already open
  });

  it('has no Reply in Sent, and cancelling restores the link', async () => {
    expect(ns.openReply(mountPreview({sent: true}))).toBe(false);
    expect(ns.cancelReply()).toBe(false);

    const root = mountPreview();
    stubFetch(() => htmlResponse(FORM));
    ns.openReply(root);
    await vi.waitFor(() => expect(form()).not.toBeNull());
    expect(ns.cancelReply()).toBe(true);
    expect(area().innerHTML).toBe('');
    expect((root.querySelector('[data-inbox-reply-link]') as HTMLElement).style.display).toBe('');
  });

  it('offers Retry when the form cannot load, which loads it again', async () => {
    mountPreview();
    stubFetch(() => htmlResponse('down', 500));
    await ns.loadReplyForm(area(), '/admin/mail/inbox/42/reply/fragment/');
    expect(area().querySelector('[role="alert"]')?.textContent).toContain('Could not load the reply form.');
    expect(area().querySelector('button[data-inbox-retry]')).not.toBeNull();

    stubFetch(() => htmlResponse(FORM));
    await ns.retryReplyForm(area());
    expect(form()).not.toBeNull();
    area().removeAttribute('data-inbox-reply-url');
    await ns.retryReplyForm(area());
  });

  it('shows and hides the Cc field', () => {
    mountPreview();
    area().innerHTML = FORM;
    const toggle = area().querySelector('[data-toggle-cc]') as HTMLElement;
    ns.toggleCc(toggle);
    expect((area().querySelector('[data-cc-row]') as HTMLElement).style.display).toBe('flex');
    expect(toggle.style.display).toBe('none');
    ns.toggleCc(toggle);
    expect((area().querySelector('[data-cc-row]') as HTMLElement).style.display).toBe('none');
    document.body.innerHTML = '';
    ns.toggleCc(toggle);
  });
});

describe('inbox-reply.js sending', () => {
  it('posts the form with the CSRF cookie and shows the confirmation as text', async () => {
    mountPreview();
    area().innerHTML = FORM;
    document.cookie = 'csrftoken=tok123';
    const fetchMock = stubFetch(() => jsonResponse(200, {ok: true, message: 'Reply sent to <b>pat@example.com</b>.'}));

    await ns.submitReplyForm(form(), area());

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe('POST');
    expect((init?.headers as Record<string, string>)['X-CSRFToken']).toBe('tok123');
    expect((init?.body as FormData).get('reply_body')).toBe('Thanks');
    expect(area().textContent).toContain('Reply sent to <b>pat@example.com</b>.');
    expect(area().querySelector('b')).toBeNull();
  });

  it('prefers the CSRF form field, and says "Reply sent." for an empty confirmation', async () => {
    mountPreview();
    area().innerHTML = `<input name="csrfmiddlewaretoken" value="field-token">${FORM}`;
    const fetchMock = stubFetch(() => jsonResponse(200, {ok: true, message: 42}));
    await ns.submitReplyForm(form(), area());
    expect((fetchMock.mock.calls[0][1]?.headers as Record<string, string>)['X-CSRFToken']).toBe('field-token');
    expect(area().textContent).toContain('Reply sent.');
  });

  it('shows the refusal or a network error and lets the user send again', async () => {
    mountPreview();
    area().innerHTML = FORM;
    stubFetch(() => jsonResponse(200, {ok: false, error: 'That address is not allowed.'}));
    await ns.submitReplyForm(form(), area());
    expect(area().querySelector('[data-inbox-reply-status]')?.textContent).toBe('That address is not allowed.');
    expect((area().querySelector('[data-inbox-send-btn]') as HTMLButtonElement).disabled).toBe(false);

    stubFetch(() => jsonResponse(200, {ok: false}));
    await ns.submitReplyForm(form(), area());
    expect(area().querySelector('[data-inbox-reply-status]')?.textContent).toBe('Failed to send.');

    stubFetch(() => Promise.reject(new TypeError('offline')));
    await ns.submitReplyForm(form(), area());
    expect(area().querySelector('[data-inbox-reply-status]')?.textContent).toBe('Network error. Please try again.');
    expect((area().querySelector('[data-inbox-send-btn]') as HTMLButtonElement).textContent).toBe('Send Reply');
  });

  it('does not post a form without an action', async () => {
    mountPreview();
    area().innerHTML = FORM;
    form().removeAttribute('data-action');
    const fetchMock = stubFetch(() => jsonResponse(200, {ok: true}));
    await ns.submitReplyForm(form(), area());
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

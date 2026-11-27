// Mail -> Inbox: the inline reply below the previewed message (admin/mail/inbox/reply/_inbox_reply_form.html).
// Extends window.I2GInbox (see inbox-state.js).
(function (ns) {
  'use strict';

  var LOADING_HTML = '<div class="flex items-center justify-center text-base-400 py-6"><span class="material-symbols-outlined ' +
    '!text-[24px] mr-2" style="animation:i2g-inbox-spin 1s linear infinite;display:inline-block;">sync</span>' +
    '<span class="text-sm">Loading reply form...</span></div>';

  ns.loadReplyForm = function (replyArea, url) {
    replyArea.setAttribute('data-inbox-reply-url', url);
    replyArea.innerHTML = LOADING_HTML;
    replyArea.style.display = 'block';
    return ns.getFragment(url)
      .then(function (html) {
        replyArea.innerHTML = html;
        if (replyArea.scrollIntoView) replyArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
        var body = replyArea.querySelector('textarea[name="reply_body"]');
        if (body) body.focus();
      })
      .catch(function () {
        replyArea.replaceChildren(ns.errorBox('Could not load the reply form.'));
      });
  };

  // Retry in the reply area loads the form again.
  ns.retryReplyForm = function (replyArea) {
    var url = replyArea.getAttribute('data-inbox-reply-url');
    return url ? ns.loadReplyForm(replyArea, url) : Promise.resolve();
  };

  // The message names the reply's addresses, which come from the original sender: it is inserted as text only,
  // never as HTML.
  ns.showReplySent = function (replyArea, message) {
    var banner = document.createElement('div');
    banner.className = 'flex items-center gap-2 py-4 text-green-600';
    var icon = document.createElement('span');
    icon.className = 'material-symbols-outlined !text-[20px]';
    icon.textContent = 'check_circle';
    var label = document.createElement('span');
    label.className = 'text-sm font-medium';
    label.textContent = typeof message === 'string' && message ? message : 'Reply sent.';
    banner.appendChild(icon);
    banner.appendChild(label);
    replyArea.textContent = '';
    replyArea.appendChild(banner);
  };

  function csrfValue() {
    var input = document.querySelector('[name=csrfmiddlewaretoken]');
    if (input && input.value) return input.value;
    var cookie = document.cookie.match(/csrftoken=([^;]+)/);
    return cookie ? cookie[1] : '';
  }

  function sendFailed(form, text) {
    var statusEl = form.querySelector('[data-inbox-reply-status]');
    var sendBtn = form.querySelector('[data-inbox-send-btn]');
    if (statusEl) {
      statusEl.className = 'mt-2 text-sm text-red-600';
      statusEl.textContent = text;
    }
    if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Send Reply'; }
  }

  ns.submitReplyForm = function (form, replyArea) {
    var actionUrl = form.getAttribute('data-action');
    if (!actionUrl) return Promise.resolve();
    var sendBtn = form.querySelector('[data-inbox-send-btn]');
    var statusEl = form.querySelector('[data-inbox-reply-status]');
    if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = 'Sending...'; }
    if (statusEl) { statusEl.className = 'mt-2 text-sm hidden'; statusEl.textContent = ''; }

    var headers = { 'X-Requested-With': 'XMLHttpRequest' };
    var token = csrfValue();
    if (token) headers['X-CSRFToken'] = token;

    return fetch(actionUrl, { method: 'POST', credentials: 'same-origin', headers: headers, body: new FormData(form) })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) ns.showReplySent(replyArea, data.message);
        else sendFailed(form, data.error || 'Failed to send.');
      })
      .catch(function () {
        sendFailed(form, 'Network error. Please try again.');
      });
  };

  ns.openReply = function (root) {
    var link = root ? root.querySelector('[data-inbox-reply-link]') : null;
    var replyArea = document.getElementById('inbox-reply-area');
    if (!link || !replyArea || link.style.display === 'none') return false;
    link.style.display = 'none';
    ns.loadReplyForm(replyArea, link.getAttribute('data-inbox-reply-link'));
    return true;
  };

  ns.cancelReply = function () {
    var replyArea = document.getElementById('inbox-reply-area');
    if (!replyArea || !replyArea.firstChild) return false;
    replyArea.innerHTML = '';
    var link = document.querySelector('[data-inbox-reply-link]');
    if (link) link.style.display = '';
    return true;
  };

  ns.toggleCc = function (ccToggle) {
    var ccRow = document.querySelector('[data-cc-row]');
    if (!ccRow) return;
    var visible = ccRow.style.display !== 'none';
    ccRow.style.display = visible ? 'none' : 'flex';
    ccToggle.style.display = visible ? '' : 'none';
    if (!visible) ccRow.querySelector('input').focus();
  };
})((window.I2GInbox = window.I2GInbox || {}));

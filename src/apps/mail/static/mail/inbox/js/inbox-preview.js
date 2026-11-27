// Mail -> Inbox: the preview pane. Loads a message's fragment, sizes its sandboxed body frame (mail wider than the
// pane widens the frame and scrolls sideways instead of being cut off) and keeps the open message in the URL hash.
// Extends window.I2GInbox (see inbox-state.js).
(function (ns) {
  'use strict';

  var MIN_FRAME_HEIGHT = 240;
  var LOADING_HTML = '<div class="flex flex-col items-center justify-center text-base-400" style="min-height:200px;">' +
    '<span class="material-symbols-outlined !text-[36px] mb-2 block" style="animation:i2g-inbox-spin 1s linear infinite;' +
    'display:inline-block;">sync</span><p class="text-sm">Loading message...</p></div>';
  var EMPTY_HTML = '<div id="inbox-preview-empty" class="i2g-inbox-empty-preview flex flex-col items-center ' +
    'justify-center text-base-400"><span class="material-symbols-outlined !text-[48px] mb-2">mail</span>' +
    '<p class="text-sm">Select a message to preview</p></div>';

  function frameDocument(iframe) {
    try {
      return iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document) || null;
    } catch (e) {
      return null;
    }
  }

  ns.initPreviewIframe = function (container) {
    var dataEl = container.querySelector('#inbox-preview-body-data');
    var iframe = container.querySelector('#inbox-preview-body');
    if (!dataEl || !iframe) return;
    try {
      iframe.onload = function () {
        ns.resizePreviewIframe();
        ns.watchPreviewIframeAssets(iframe);
      };
      iframe.srcdoc = JSON.parse(dataEl.textContent);
    } catch (e) {}
    window.setTimeout(ns.resizePreviewIframe, 50);
  };

  // The frame's content size; the frame itself never scrolls (its height follows the content).
  ns.getPreviewIframeSize = function (iframe) {
    var doc = frameDocument(iframe);
    if (!doc || !doc.body || !doc.documentElement) return { width: 0, height: 0 };
    doc.documentElement.style.overflow = 'hidden';
    doc.body.style.overflow = 'hidden';
    var body = doc.body;
    var html = doc.documentElement;
    return {
      width: Math.max(body.scrollWidth, html.scrollWidth),
      height: Math.max(body.scrollHeight, body.offsetHeight, html.clientHeight, html.scrollHeight, html.offsetHeight),
    };
  };

  ns.watchPreviewIframeAssets = function (iframe) {
    var doc = frameDocument(iframe);
    if (!doc) return;
    doc.querySelectorAll('img').forEach(function (image) {
      if (!image.complete) {
        image.addEventListener('load', ns.resizePreviewIframe, { once: true });
        image.addEventListener('error', ns.resizePreviewIframe, { once: true });
      }
    });
  };

  ns.resizePreviewIframe = function () {
    var iframe = document.getElementById('inbox-preview-body');
    if (!iframe) return;
    iframe.style.width = '100%';
    var available = iframe.clientWidth;
    var size = ns.getPreviewIframeSize(iframe);
    // Wide mail (a 700px newsletter in a 590px pane): the frame takes the mail's width and its wrapper scrolls.
    if (available && size.width > available + 1) iframe.style.width = size.width + 'px';
    iframe.style.height = Math.max(size.height, MIN_FRAME_HEIGHT) + 'px';
  };

  ns.getHashUid = function () {
    var m = location.hash.match(/^#msg=(.+)/);
    if (!m) return null;
    try {
      return decodeURIComponent(m[1]);
    } catch (e) {
      return null;
    }
  };

  ns.setHashUid = function (uid) {
    if (uid) history.replaceState(null, '', '#msg=' + encodeURIComponent(uid));
    else history.replaceState(null, '', location.pathname + location.search);
  };

  ns.clearPreviewPane = function (root) {
    var content = root ? root.querySelector('#inbox-preview-content') : null;
    if (content) content.innerHTML = EMPTY_HTML;
    if (root) ns.setActiveRow(root, null);
  };

  ns.loadPreview = function (root, row) {
    var pane = root.querySelector('#inbox-preview-pane');
    var content = root.querySelector('#inbox-preview-content');
    var url = row.getAttribute('data-preview-url');
    if (!pane || !content || !url) return Promise.resolve();
    var uid = row.getAttribute('data-uid');

    ns.setActiveRow(root, uid);
    ns.setHashUid(uid);
    ns.rememberOpened(uid);
    ns.markOpened(row);
    content.innerHTML = LOADING_HTML;
    pane.classList.add('is-loading');

    return ns.getFragment(url)
      .then(function (html) {
        content.innerHTML = html;
        ns.initPreviewIframe(content);
      })
      .catch(function () {
        content.replaceChildren(ns.errorBox('Could not load the message. Check your connection and try again.'));
      })
      .finally(function () {
        pane.classList.remove('is-loading');
      });
  };

  // Retry in the preview pane: the message that is open (active) is loaded again.
  ns.retryPreview = function (root) {
    var row = root.querySelector('[data-inbox-row].is-active');
    return row ? ns.loadPreview(root, row) : Promise.resolve();
  };

  // Opening a message here never marks it read in the mailbox (Gmail and Outlook keep their state, and so does the
  // unread count); the row only stops looking unread in this tab.
  ns.markOpened = function (row) {
    if (!row || !row.classList.contains('is-unread')) return;
    row.classList.remove('is-unread');
    row.classList.add('is-opened');
    var icon = row.querySelector('[data-inbox-row-icon]');
    if (icon) {
      icon.textContent = 'drafts';
      icon.setAttribute('title', 'Opened here; still unread in the mailbox');
    }
  };

  ns.markOpenedRows = function (root) {
    var opened = ns.openedUids();
    if (!opened.length) return;
    root.querySelectorAll('[data-inbox-row].is-unread').forEach(function (row) {
      if (opened.indexOf(row.getAttribute('data-uid')) !== -1) ns.markOpened(row);
    });
  };
})((window.I2GInbox = window.I2GInbox || {}));

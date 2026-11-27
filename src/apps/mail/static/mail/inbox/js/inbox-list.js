// Mail -> Inbox: loading the message list (the fragment view), merging a refreshed list into the page (rows of
// "Load older" pages survive the auto-refresh), and failures shown in the page with Retry. Extends window.I2GInbox
// (see inbox-state.js).
(function (ns) {
  'use strict';

  var SCROLL_KEY = 'inbox-list-scroll';
  var REQUEST_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' };

  ns.fragmentText = function (response) {
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.text();
  };

  ns.getFragment = function (url) {
    return fetch(url, { credentials: 'same-origin', headers: REQUEST_HEADERS }).then(ns.fragmentText);
  };

  function rowsOf(container) {
    return Array.prototype.slice.call(container.querySelectorAll('[data-inbox-row]'));
  }

  // A refreshed first page, when older pages are loaded too: rows it has replace theirs in place, new rows go on
  // top, and every older row stays.
  function mergeRows(list, freshList) {
    var existing = {};
    rowsOf(list).forEach(function (row) { existing[row.getAttribute('data-uid')] = row; });
    var top = list.querySelector('[data-inbox-row]') || list.querySelector('[data-inbox-list-footer]');
    rowsOf(freshList).forEach(function (row) {
      var old = existing[row.getAttribute('data-uid')];
      if (old) old.replaceWith(row);
      else if (top) list.insertBefore(row, top);
      else list.appendChild(row);
    });
  }

  // options.keepOlder (the auto-refresh): rows of older pages stay; otherwise the list becomes the first page again.
  ns.mergeListHtml = function (root, html, options) {
    var tmp = document.createElement('div');
    tmp.innerHTML = html;

    function replaceSection(selector) {
      var fresh = tmp.querySelector(selector);
      var current = root.querySelector(selector);
      if (fresh && current) {
        current.replaceWith(fresh);
      } else if (!fresh && current) {
        current.remove();
      } else if (fresh) {
        var shell = root.querySelector('.i2g-mail-shell');
        var split = shell ? shell.querySelector('.i2g-inbox-split') : null;
        if (shell && split) shell.insertBefore(fresh, split);
      }
    }

    ['.i2g-mail-toolbar', '[data-inbox-account-panel]', '[data-inbox-hidden]', '[data-inbox-status]',
      '[data-inbox-list-error]', '.i2g-inbox-list-head'].forEach(replaceSection);

    var newList = tmp.querySelector('.i2g-inbox-list');
    var oldList = root.querySelector('.i2g-inbox-list');
    if (newList && oldList) {
      if (options && options.keepOlder && Number(oldList.getAttribute('data-inbox-pages') || '1') > 1) {
        mergeRows(oldList, newList);
      } else {
        oldList.innerHTML = newList.innerHTML;
        oldList.setAttribute('data-inbox-pages', '1');
      }
    }

    var newSplit = tmp.querySelector('.i2g-inbox-split');
    if (!root.querySelector('.i2g-inbox-split') && newSplit) {
      var shell = root.querySelector('.i2g-mail-shell');
      var previewPane = root.querySelector('#inbox-preview-pane');
      if (shell && previewPane) {
        var freshPreview = newSplit.querySelector('#inbox-preview-pane');
        if (freshPreview) freshPreview.replaceWith(previewPane);
        shell.appendChild(newSplit);
      }
    }
    ns.applyLayoutState(root);
  };

  function listScroll(root) {
    var list = root.querySelector('.i2g-inbox-list');
    return list ? list.scrollTop : 0;
  }

  function restoreListScroll(root, top) {
    var list = root.querySelector('.i2g-inbox-list');
    if (list && top) list.scrollTop = top;
  }

  ns.persistScrollToSession = function (root) {
    try { sessionStorage.setItem(SCROLL_KEY, String(listScroll(root))); } catch (e) {}
  };

  function popSessionScroll() {
    try {
      var v = sessionStorage.getItem(SCROLL_KEY);
      sessionStorage.removeItem(SCROLL_KEY);
      return v ? Number(v) : 0;
    } catch (e) { return 0; }
  }

  // A list that could not be refreshed keeps what it shows, with a note and Retry (never a browser alert).
  ns.showListError = function (root, message) {
    var skel = root.querySelector('#inbox-loading-skeleton');
    var target = skel || root.querySelector('.i2g-mail-shell');
    if (!target) return;
    var old = root.querySelector('[data-inbox-list-error]');
    if (old) old.remove();
    var box = ns.errorBox(message, 'data-inbox-refresh');
    box.setAttribute('data-inbox-list-error', '');
    if (skel) skel.replaceChildren(box);
    else target.insertBefore(box, target.querySelector('.i2g-inbox-split'));
  };

  // What the user sees of a failure: the message as text, and a Retry button carrying `retryAttribute`.
  ns.errorBox = function (message, retryAttribute) {
    var box = document.createElement('div');
    box.className = 'i2g-inbox-fragment-error';
    box.setAttribute('role', 'alert');
    var text = document.createElement('span');
    text.className = 'i2g-inbox-fragment-error__text';
    text.textContent = message;
    var retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'i2g-inbox-retry-btn cursor-pointer font-sans';
    retry.setAttribute(retryAttribute || 'data-inbox-retry', '');
    retry.textContent = 'Retry';
    box.appendChild(text);
    box.appendChild(retry);
    return box;
  };

  // options.quiet (the auto-refresh): no spinner, no error note, and the list is merged in place, so it keeps its
  // scroll position and the pages "Load older" added.
  ns.fetchInbox = function (root, params, options) {
    var url = root.getAttribute('data-fragment-url');
    if (!url) return Promise.resolve();
    var quiet = !!(options && options.quiet);
    var activeUid = ns.getActiveUid(root);
    var merge = ns.hasPreviewContent(root) || (quiet && !!root.querySelector('[data-inbox-list]'));
    var scrollTop = listScroll(root);
    var sessionScroll = merge ? 0 : popSessionScroll();
    var btn = quiet ? null : root.querySelector('[data-inbox-refresh]');
    if (btn) {
      btn.classList.add('i2g-inbox-refresh--loading');
      btn.setAttribute('disabled', 'disabled');
    }
    return ns.getFragment(ns.buildUrl(url, params || {}))
      .then(function (html) {
        if (merge) {
          ns.mergeListHtml(root, html, { keepOlder: quiet });
          if (activeUid) ns.setActiveRow(root, activeUid);
          restoreListScroll(root, scrollTop);
        } else {
          root.innerHTML = html;
          var savedRow = ns.rowByUid(root, ns.getHashUid());
          if (savedRow) {
            ns.loadPreview(root, savedRow);
            restoreListScroll(root, sessionScroll);
          }
        }
        ns.applyLayoutState(root);
        ns.markOpenedRows(root);
        ns.applyFilter(root);
      })
      .catch(function () {
        if (!quiet) ns.showListError(root, 'Could not load the inbox. Check your connection and try again.');
      })
      .finally(function () {
        var current = root.querySelector('[data-inbox-refresh][disabled]');
        if (current) { current.classList.remove('i2g-inbox-refresh--loading'); current.removeAttribute('disabled'); }
      });
  };

  ns.rowByUid = function (root, uid) {
    if (!uid) return null;
    var escaped = window.CSS && CSS.escape ? CSS.escape(uid) : uid.replace(/["\\]/g, '\\$&');
    return root.querySelector('[data-inbox-row][data-uid="' + escaped + '"]');
  };

  ns.setActiveRow = function (root, uid) {
    root.querySelectorAll('[data-inbox-row]').forEach(function (r) {
      r.classList.toggle('is-active', r.getAttribute('data-uid') === uid);
    });
  };
})((window.I2GInbox = window.I2GInbox || {}));

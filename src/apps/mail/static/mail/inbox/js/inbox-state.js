// Mail -> Inbox (admin/mail/inbox/list/list.html): shared state for the inbox scripts, which extend window.I2GInbox
// and load in this order: inbox-state, inbox-list, inbox-filter, inbox-preview, inbox-reply, inbox-keys, inbox-boot.
// Here: URLs, what the browser remembers (localStorage / sessionStorage) and the shell's layout state.
(function (ns) {
  'use strict';

  var KEYS = {
    account: 'i2g-inbox-account',
    accountCollapsed: 'i2g-inbox-account-collapsed',
    folder: 'i2g-inbox-folder',
    limit: 'i2g-inbox-limit',
    listCollapsed: 'i2g-inbox-list-collapsed',
  };
  // Messages opened in this tab: previewing never marks a message read in the mailbox, so only the row changes.
  var OPENED_KEY = 'i2g-inbox-opened';
  var OPENED_MAX = 500;

  function read(store, key, fallback) {
    try {
      var value = window[store].getItem(key);
      return value === null ? fallback : value;
    } catch (e) {
      return fallback;
    }
  }

  function write(store, key, value) {
    try {
      window[store].setItem(key, value);
    } catch (e) {}
  }

  ns.buildUrl = function (base, params) {
    var qs = [];
    for (var k in params) {
      if (params[k]) qs.push(k + '=' + encodeURIComponent(params[k]));
    }
    if (!qs.length) return base;
    return base + (base.indexOf('?') === -1 ? '?' : '&') + qs.join('&');
  };

  ns.getRoot = function (el) {
    return el ? el.closest('#inbox-all-dynamic') : null;
  };

  ns.storedFolder = function () {
    return read('localStorage', KEYS.folder, 'INBOX') === 'SENT' ? 'SENT' : 'INBOX';
  };
  ns.storeFolder = function (folder) {
    write('localStorage', KEYS.folder, folder === 'SENT' ? 'SENT' : 'INBOX');
  };

  // The universal inbox shows every account ('all') or one account key; the server ignores an unknown key.
  ns.storedAccount = function () {
    return read('localStorage', KEYS.account, '') || 'all';
  };
  ns.storeAccount = function (account) {
    write('localStorage', KEYS.account, account || 'all');
  };

  // The chosen page size; the server accepts only its own choices and falls back to its default.
  ns.storedLimit = function () {
    var value = read('localStorage', KEYS.limit, '');
    return /^[0-9]{1,3}$/.test(value) ? value : '';
  };
  ns.storeLimit = function (limit) {
    if (/^[0-9]{1,3}$/.test(String(limit || ''))) write('localStorage', KEYS.limit, String(limit));
  };

  // The details panel is collapsed unless the user opened it ('0').
  ns.storedAccountCollapsed = function () {
    return read('localStorage', KEYS.accountCollapsed, '1') !== '0';
  };
  ns.storeAccountCollapsed = function (collapsed) {
    write('localStorage', KEYS.accountCollapsed, collapsed ? '1' : '0');
  };

  ns.storedListCollapsed = function () {
    return read('localStorage', KEYS.listCollapsed, '0') === '1';
  };
  ns.storeListCollapsed = function (collapsed) {
    write('localStorage', KEYS.listCollapsed, collapsed ? '1' : '0');
  };

  ns.openedUids = function () {
    try {
      var list = JSON.parse(read('sessionStorage', OPENED_KEY, '[]'));
      return Array.isArray(list) ? list.filter(function (uid) { return typeof uid === 'string'; }) : [];
    } catch (e) {
      return [];
    }
  };
  ns.rememberOpened = function (uid) {
    if (!uid) return;
    var list = ns.openedUids().filter(function (item) { return item !== uid; });
    list.push(uid);
    write('sessionStorage', OPENED_KEY, JSON.stringify(list.slice(-OPENED_MAX)));
  };

  ns.getAccount = function (root) {
    var sel = root ? root.querySelector('[data-inbox-account]') : null;
    return sel ? sel.value : ns.storedAccount();
  };

  ns.getFolder = function (root) {
    var activeTab = root ? root.querySelector('[data-inbox-folder].i2g-mail-folder-tab--active') : null;
    if (activeTab) return activeTab.getAttribute('data-inbox-folder') === 'SENT' ? 'SENT' : 'INBOX';
    return ns.storedFolder();
  };

  ns.getLimit = function (root) {
    var sel = root ? root.querySelector('[data-inbox-limit]') : null;
    return sel ? sel.value : ns.storedLimit();
  };

  // The query every list request sends: what is shown now, plus `extra`.
  ns.listParams = function (root, extra) {
    var params = { limit: ns.getLimit(root), folder: ns.getFolder(root), account: ns.getAccount(root) };
    for (var k in extra || {}) params[k] = extra[k];
    return params;
  };

  ns.setActiveFolderTab = function (root, folder) {
    if (!root) return;
    root.querySelectorAll('[data-inbox-folder]').forEach(function (tab) {
      var active = tab.getAttribute('data-inbox-folder') === folder;
      tab.classList.toggle('i2g-mail-folder-tab--active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
  };

  function shellOf(root) {
    return root ? root.querySelector('.i2g-mail-shell') : null;
  }

  ns.setAccountCollapsed = function (root, collapsed) {
    var shell = shellOf(root);
    if (!shell) return;
    shell.classList.toggle('is-account-collapsed', collapsed);
    var toggle = shell.querySelector('[data-inbox-account-toggle]');
    if (toggle) toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    var label = shell.querySelector('[data-inbox-account-toggle-label]');
    if (label) label.textContent = collapsed ? 'Show details' : 'Hide details';
  };

  ns.setListCollapsed = function (root, collapsed) {
    var shell = shellOf(root);
    if (!shell) return;
    shell.classList.toggle('is-list-collapsed', collapsed);
    var toggle = shell.querySelector('[data-inbox-list-toggle]');
    if (toggle) {
      var text = collapsed ? 'Expand message list' : 'Collapse message list';
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      toggle.setAttribute('aria-label', text);
      toggle.setAttribute('title', text);
    }
    var icon = shell.querySelector('.i2g-inbox-list-toggle__icon');
    if (icon) icon.textContent = collapsed ? 'chevron_right' : 'chevron_left';
  };

  ns.applyLayoutState = function (root) {
    ns.setAccountCollapsed(root, ns.storedAccountCollapsed());
    ns.setListCollapsed(root, ns.storedListCollapsed());
    if (ns.resizePreviewIframe) ns.resizePreviewIframe();
  };

  ns.getActiveUid = function (root) {
    var active = root.querySelector('[data-inbox-row].is-active');
    return active ? active.getAttribute('data-uid') : null;
  };

  ns.hasPreviewContent = function (root) {
    var content = root.querySelector('#inbox-preview-content');
    return !!content && !content.querySelector('#inbox-preview-empty');
  };
})((window.I2GInbox = window.I2GInbox || {}));

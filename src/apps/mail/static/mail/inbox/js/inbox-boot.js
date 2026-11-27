// Mail -> Inbox: wires the page up (event delegation on document.body), loads the first list with the folder,
// account and page size this browser remembers, and refreshes the list while the page is visible. Loads last; the
// other inbox scripts extend window.I2GInbox (see inbox-state.js).
(function (ns) {
  'use strict';

  function toggleList(root) {
    var shell = root.querySelector('.i2g-mail-shell');
    var collapsed = shell ? !shell.classList.contains('is-list-collapsed') : false;
    ns.setListCollapsed(root, collapsed);
    ns.storeListCollapsed(collapsed);
    ns.resizePreviewIframe();
  }

  function toggleAccountPanel(root) {
    var shell = root.querySelector('.i2g-mail-shell');
    var collapsed = shell ? !shell.classList.contains('is-account-collapsed') : false;
    ns.setAccountCollapsed(root, collapsed);
    ns.storeAccountCollapsed(collapsed);
  }

  // A Ctrl / Cmd / Shift / Alt click opens the row's link the browser's way (a new tab or window); a middle click
  // fires no click event at all, so it opens a new tab as on any link.
  function opensElsewhere(e) {
    return e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey;
  }

  function retry(button) {
    var replyArea = button.closest('#inbox-reply-area');
    if (replyArea) return ns.retryReplyForm(replyArea);
    var root = ns.getRoot(button);
    return root ? ns.retryPreview(root) : null;
  }

  ns.onClick = function (e) {
    var target = e.target;
    var root = ns.getRoot(target);
    var el;
    if ((el = target.closest('[data-inbox-list-toggle]'))) {
      e.preventDefault();
      if (root) toggleList(root);
    } else if ((el = target.closest('[data-inbox-account-toggle]'))) {
      e.preventDefault();
      if (root) toggleAccountPanel(root);
    } else if ((el = target.closest('[data-inbox-folder]'))) {
      e.preventDefault();
      var folder = el.getAttribute('data-inbox-folder') === 'SENT' ? 'SENT' : 'INBOX';
      if (!root || folder === ns.getFolder(root)) return;
      ns.storeFolder(folder);
      ns.setActiveFolderTab(root, folder);
      // A uid is unique only within its folder, so drop the open preview/hash. The list comes from the cache
      // when it is fresh (no refresh=1): switching back and forth reads no mailbox.
      ns.clearPreviewPane(root);
      ns.setHashUid(null);
      ns.fetchInbox(root, ns.listParams(root, { folder: folder }));
    } else if ((el = target.closest('[data-inbox-refresh]'))) {
      e.preventDefault();
      if (root) ns.fetchInbox(root, ns.listParams(root, { refresh: '1' }));
    } else if ((el = target.closest('[data-inbox-older]'))) {
      e.preventDefault();
      if (root) ns.loadOlder(root, el);
    } else if ((el = target.closest('[data-inbox-unread-only]'))) {
      e.preventDefault();
      if (root) ns.toggleUnreadOnly(root);
    } else if ((el = target.closest('[data-inbox-retry]'))) {
      e.preventDefault();
      retry(el);
    } else if ((el = target.closest('[data-inbox-reply-link]'))) {
      e.preventDefault();
      ns.openReply(root || document);
    } else if ((el = target.closest('[data-toggle-cc]'))) {
      e.preventDefault();
      ns.toggleCc(el);
    } else if ((el = target.closest('[data-inbox-cancel-reply]'))) {
      e.preventDefault();
      ns.cancelReply();
    } else if ((el = target.closest('[data-inbox-row]'))) {
      if (!root || opensElsewhere(e)) return;
      e.preventDefault();
      if (root.querySelector('#inbox-preview-pane')) ns.loadPreview(root, el);
      else window.location.href = el.getAttribute('href');
    }
  };

  ns.onChange = function (e) {
    var root = ns.getRoot(e.target);
    if (!root) return;
    if (e.target.closest('[data-inbox-account]')) {
      ns.storeAccount(e.target.value);
      // The open message belongs to the previous selection: drop the preview/hash.
      ns.clearPreviewPane(root);
      ns.setHashUid(null);
      ns.fetchInbox(root, ns.listParams(root));
    } else if (e.target.closest('[data-inbox-limit]')) {
      ns.storeLimit(e.target.value);
      ns.fetchInbox(root, ns.listParams(root));
    }
  };

  /* Auto-refresh: the server polls every mailbox for new mail in the background; while this page is visible it
     reloads its list (served from that poll, so it seldom connects to a mailbox). Skipped while a reply is being
     written or a load is already running. */
  function autoRefreshSeconds(root) {
    var shell = root ? root.querySelector('[data-inbox-auto-refresh]') : null;
    var value = shell ? parseInt(shell.getAttribute('data-inbox-auto-refresh'), 10) : 0;
    return value > 0 ? value : 0;
  }

  var lastAutoRefresh = Date.now();
  ns.autoRefreshTick = function () {
    var root = document.getElementById('inbox-all-dynamic');
    var seconds = autoRefreshSeconds(root);
    if (!root || !seconds || document.hidden) return false;
    if (Date.now() - lastAutoRefresh < seconds * 1000) return false;
    if (root.querySelector('#inbox-reply-area form')) return false;
    if (root.querySelector('[data-inbox-refresh][disabled], [data-inbox-older][disabled]')) return false;
    lastAutoRefresh = Date.now();
    ns.fetchInbox(root, ns.listParams(root), { quiet: true });
    return true;
  };

  document.body.addEventListener('click', ns.onClick);
  document.body.addEventListener('change', ns.onChange);
  document.body.addEventListener('input', function (e) {
    if (e.target.closest('[data-inbox-filter]')) ns.setFilterQuery(ns.getRoot(e.target), e.target.value);
  });
  document.body.addEventListener('submit', function (e) {
    var form = e.target.closest('[data-inbox-reply-form]');
    var replyArea = document.getElementById('inbox-reply-area');
    if (!form) return;
    e.preventDefault();
    if (replyArea) ns.submitReplyForm(form, replyArea);
  });
  document.addEventListener('keydown', function (e) {
    if (ns.handleKey(e)) e.preventDefault();
  });
  window.addEventListener('resize', ns.resizePreviewIframe);
  window.addEventListener('beforeunload', function () {
    var root = document.getElementById('inbox-all-dynamic');
    if (root) ns.persistScrollToSession(root);
  });
  window.setInterval(ns.autoRefreshTick, 5000);

  var root = document.getElementById('inbox-all-dynamic');
  if (root) {
    ns.fetchInbox(root, { folder: ns.storedFolder(), account: ns.storedAccount(), limit: ns.storedLimit() });
  }
})((window.I2GInbox = window.I2GInbox || {}));

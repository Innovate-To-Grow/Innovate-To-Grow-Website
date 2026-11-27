// Mail -> Inbox: keyboard shortcuts, as in Gmail. j / k open the next / previous message, Enter opens the selected
// one, r replies, Esc closes the reply (or the message), / goes to the quick filter. Keys typed into a field, or
// with Ctrl / Cmd / Alt held, are left alone. Extends window.I2GInbox (see inbox-state.js).
(function (ns) {
  'use strict';

  function isTyping(target) {
    if (!target || !target.closest) return false;
    return !!target.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]');
  }

  function currentRow(root, rows) {
    var focused = document.activeElement && document.activeElement.closest
      ? document.activeElement.closest('[data-inbox-row]')
      : null;
    if (focused && rows.indexOf(focused) !== -1) return focused;
    var active = root.querySelector('[data-inbox-row].is-active');
    return active && rows.indexOf(active) !== -1 ? active : null;
  }

  function openRow(root, row) {
    if (!row) return;
    if (row.focus) row.focus({ preventScroll: true });
    if (row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
    ns.loadPreview(root, row);
  }

  // The row `delta` steps from the current one among the rows the filter shows (the first one when none is).
  ns.stepRow = function (root, delta) {
    var rows = ns.visibleRows(root);
    if (!rows.length) return null;
    var current = currentRow(root, rows);
    if (!current) return delta < 0 ? rows[rows.length - 1] : rows[0];
    var index = rows.indexOf(current) + delta;
    return rows[Math.max(0, Math.min(rows.length - 1, index))];
  };

  function closeMessage(root) {
    if (ns.cancelReply()) return true;
    if (!ns.hasPreviewContent(root)) return false;
    ns.clearPreviewPane(root);
    ns.setHashUid(null);
    return true;
  }

  // Returns true when the key was handled (the caller then prevents its default).
  ns.handleKey = function (event) {
    var root = document.getElementById('inbox-all-dynamic');
    if (!root || event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return false;
    var filter = root.querySelector('[data-inbox-filter]');
    if (event.key === 'Escape' && filter && event.target === filter) {
      ns.setFilterQuery(root, '');
      filter.blur();
      return true;
    }
    if (isTyping(event.target)) return false;
    switch (event.key) {
      case 'j':
        openRow(root, ns.stepRow(root, 1));
        return true;
      case 'k':
        openRow(root, ns.stepRow(root, -1));
        return true;
      case 'Enter': {
        // Enter on a focused row is the link's own click (handled like a click on it).
        if (event.target && event.target.closest && event.target.closest('a, button')) return false;
        var rows = ns.visibleRows(root);
        openRow(root, currentRow(root, rows) || rows[0]);
        return true;
      }
      case 'r':
        return ns.openReply(root);
      case 'Escape':
        return closeMessage(root);
      case '/':
        if (!filter) return false;
        filter.focus();
        return true;
      default:
        return false;
    }
  };
})((window.I2GInbox = window.I2GInbox || {}));

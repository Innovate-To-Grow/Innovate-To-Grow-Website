// Mail -> Inbox: the list's own controls. The quick filter and "Unread only" hide loaded rows in the browser (the
// server is not searched); "Load older" appends the next page, whose cursor the server put on the button.
// Extends window.I2GInbox (see inbox-state.js).
(function (ns) {
  'use strict';

  // Kept while the list is reloaded (the filter bar is rendered again with each full list).
  ns.filterState = { query: '', unreadOnly: false };

  function normalize(text) {
    return String(text || '').toLowerCase().replace(/\s+/g, ' ').trim();
  }

  // What the filter searches: sender (or recipient in Sent), subject and snippet.
  ns.rowText = function (row) {
    var parts = row.querySelectorAll('[data-inbox-row-sender], [data-inbox-row-subject], [data-inbox-row-snippet]');
    if (!parts.length) return normalize(row.textContent);
    return normalize(Array.prototype.map.call(parts, function (part) { return part.textContent; }).join(' '));
  };

  ns.rowMatches = function (row, state) {
    if (state.unreadOnly && !row.classList.contains('is-unread')) return false;
    var words = normalize(state.query).split(' ').filter(Boolean);
    if (!words.length) return true;
    var text = ns.rowText(row);
    return words.every(function (word) { return text.indexOf(word) !== -1; });
  };

  function syncControls(root) {
    var input = root.querySelector('[data-inbox-filter]');
    if (input && input.value !== ns.filterState.query) input.value = ns.filterState.query;
    var toggle = root.querySelector('[data-inbox-unread-only]');
    if (toggle) toggle.setAttribute('aria-pressed', ns.filterState.unreadOnly ? 'true' : 'false');
  }

  // Hide the rows that do not match, say so when none does, and keep the count true ("3 of 30 loaded").
  ns.applyFilter = function (root) {
    if (!root) return;
    syncControls(root);
    var rows = root.querySelectorAll('[data-inbox-row]');
    var shown = 0;
    rows.forEach(function (row) {
      var match = ns.rowMatches(row, ns.filterState);
      row.hidden = !match;
      if (match) shown += 1;
    });
    var filtering = !!(ns.filterState.unreadOnly || normalize(ns.filterState.query));
    var empty = root.querySelector('[data-inbox-filter-empty]');
    if (empty) empty.hidden = !(filtering && rows.length && !shown);
    var count = root.querySelector('[data-inbox-count]');
    if (count) count.textContent = (filtering ? shown + ' of ' : '') + rows.length + ' loaded';
  };

  ns.setFilterQuery = function (root, query) {
    ns.filterState.query = String(query || '');
    ns.applyFilter(root);
  };

  ns.toggleUnreadOnly = function (root, value) {
    ns.filterState.unreadOnly = typeof value === 'boolean' ? value : !ns.filterState.unreadOnly;
    ns.applyFilter(root);
  };

  ns.visibleRows = function (root) {
    return Array.prototype.filter.call(root.querySelectorAll('[data-inbox-row]'), function (row) {
      return !row.hidden;
    });
  };

  function setOlderBusy(button, busy, label) {
    button.disabled = busy;
    var text = button.querySelector('[data-inbox-older-label]');
    if (text) text.textContent = label;
  }

  // Append the page after the one `button` ends (rows already listed are skipped) and swap in its footer.
  ns.loadOlder = function (root, button) {
    var url = root.getAttribute('data-fragment-url');
    var list = root.querySelector('[data-inbox-list]');
    if (!url || !list || button.disabled) return Promise.resolve();
    setOlderBusy(button, true, 'Loading...');
    var params = ns.listParams(root, { older: '1', cursor: button.getAttribute('data-inbox-older') });
    return ns.getFragment(ns.buildUrl(url, params))
      .then(function (html) {
        var tmp = document.createElement('div');
        tmp.innerHTML = html;
        var footer = list.querySelector('[data-inbox-list-footer]');
        tmp.querySelectorAll('[data-inbox-row]').forEach(function (row) {
          if (ns.rowByUid(list, row.getAttribute('data-uid'))) return;
          if (footer) list.insertBefore(row, footer);
          else list.appendChild(row);
        });
        var freshFooter = tmp.querySelector('[data-inbox-list-footer]');
        if (footer && freshFooter) footer.replaceWith(freshFooter);
        else if (freshFooter) list.appendChild(freshFooter);
        list.setAttribute('data-inbox-pages', String(Number(list.getAttribute('data-inbox-pages') || '1') + 1));
        ns.markOpenedRows(root);
        ns.applyFilter(root);
      })
      .catch(function () {
        setOlderBusy(button, false, 'Retry');
        var footer = button.closest('[data-inbox-list-footer]');
        if (footer && !footer.querySelector('[data-inbox-older-error]')) {
          var note = document.createElement('p');
          note.className = 'i2g-inbox-list-footer__error';
          note.setAttribute('data-inbox-older-error', '');
          note.setAttribute('role', 'alert');
          note.textContent = 'Could not load older messages.';
          footer.insertBefore(note, button);
        }
      });
  };
})((window.I2GInbox = window.I2GInbox || {}));

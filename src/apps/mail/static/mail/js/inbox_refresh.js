(function () {
  'use strict';

  function closest(el, selector) {
    if (!el || !el.closest) return null;
    return el.closest(selector);
  }

  function getLimit(root) {
    var sel = root.querySelector('[data-inbox-limit]');
    return sel ? sel.value : '';
  }

  function buildUrl(base, params) {
    var qs = [];
    for (var k in params) {
      if (params[k]) qs.push(k + '=' + encodeURIComponent(params[k]));
    }
    if (!qs.length) return base;
    var sep = base.indexOf('?') === -1 ? '?' : '&';
    return base + sep + qs.join('&');
  }

  /* ── Inbox list refresh ── */

  function getActiveUid(root) {
    var active = root.querySelector('[data-inbox-row].is-active');
    return active ? active.getAttribute('data-uid') : null;
  }

  function hasPreviewContent(root) {
    var content = root.querySelector('#inbox-preview-content');
    if (!content) return false;
    return !content.querySelector('#inbox-preview-empty');
  }

  function mergeListHtml(root, html) {
    var tmp = document.createElement('div');
    tmp.innerHTML = html;

    var newList = tmp.querySelector('.i2g-inbox-list');
    var oldList = root.querySelector('.i2g-inbox-list');
    if (newList && oldList) {
      oldList.innerHTML = newList.innerHTML;
    }

    var configSections = tmp.querySelectorAll(':scope > div:not(.i2g-inbox-split)');
    var oldConfigs = root.querySelectorAll(':scope > div:not(.i2g-inbox-split)');
    configSections.forEach(function (newDiv, i) {
      if (oldConfigs[i]) oldConfigs[i].innerHTML = newDiv.innerHTML;
    });
  }

  function saveListScroll(root) {
    var list = root.querySelector('.i2g-inbox-list');
    return list ? list.scrollTop : 0;
  }

  function restoreListScroll(root, top) {
    var list = root.querySelector('.i2g-inbox-list');
    if (list && top) list.scrollTop = top;
  }

  function refreshInbox(root) {
    var url = root.getAttribute('data-fragment-url');
    if (!url) return;
    var limit = getLimit(root);
    var activeUid = getActiveUid(root);
    var preservePreview = hasPreviewContent(root);
    var scrollTop = saveListScroll(root);
    var btn = root.querySelector('[data-inbox-refresh]');
    if (btn) {
      btn.classList.add('i2g-inbox-refresh--loading');
      btn.setAttribute('disabled', 'disabled');
    }

    fetch(buildUrl(url, {limit: limit}), {
      credentials: 'same-origin',
      headers: {'X-Requested-With': 'XMLHttpRequest'},
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Request failed');
        return r.text();
      })
      .then(function (html) {
        if (preservePreview) {
          mergeListHtml(root, html);
          if (activeUid) setActiveRow(root, activeUid);
          restoreListScroll(root, scrollTop);
        } else {
          root.innerHTML = html;
        }
      })
      .catch(function () {
        window.alert('Could not refresh inbox. Please try again.');
      })
      .finally(function () {
        if (btn) {
          btn.classList.remove('i2g-inbox-refresh--loading');
          btn.removeAttribute('disabled');
        }
      });
  }

  /* ── Preview pane ── */

  function isPreviewVisible() {
    var pane = document.getElementById('inbox-preview-pane');
    if (!pane) return false;
    return pane.offsetWidth > 0;
  }

  function setActiveRow(root, uid) {
    var rows = root.querySelectorAll('[data-inbox-row]');
    for (var i = 0; i < rows.length; i++) {
      rows[i].classList.toggle('is-active', rows[i].getAttribute('data-uid') === uid);
    }
  }

  function loadPreview(root, row) {
    var pane = document.getElementById('inbox-preview-pane');
    var content = document.getElementById('inbox-preview-content');
    if (!pane || !content) return false;

    var url = row.getAttribute('data-preview-url');
    var uid = row.getAttribute('data-uid');
    if (!url) return false;

    setActiveRow(root, uid);
    pane.classList.add('is-loading');

    fetch(url, {
      credentials: 'same-origin',
      headers: {'X-Requested-With': 'XMLHttpRequest'},
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Request failed');
        return r.text();
      })
      .then(function (html) {
        content.innerHTML = html;
      })
      .catch(function () {
        content.innerHTML = '<div class="p-4 text-sm text-red-600">Failed to load message.</div>';
      })
      .finally(function () {
        pane.classList.remove('is-loading');
      });

    return true;
  }

  /* ── Event delegation ── */

  document.body.addEventListener('click', function (e) {
    // Refresh button
    var btn = closest(e.target, '[data-inbox-refresh]');
    if (btn) {
      e.preventDefault();
      var root = closest(btn, '#inbox-all-dynamic');
      if (root) refreshInbox(root);
      return;
    }

    // Row click → preview (on large screens) or navigate (on small screens)
    var row = closest(e.target, '[data-inbox-row]');
    if (row) {
      var root = closest(row, '#inbox-all-dynamic');
      if (root && isPreviewVisible()) {
        e.preventDefault();
        loadPreview(root, row);
      }
      // On small screens, let the native <a> navigate to the detail page
    }
  });

  document.body.addEventListener('change', function (e) {
    var sel = closest(e.target, '[data-inbox-limit]');
    if (!sel) return;
    var root = closest(sel, '#inbox-all-dynamic');
    if (root) refreshInbox(root);
  });
})();

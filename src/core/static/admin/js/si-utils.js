/**
 * System Intelligence — shared utilities.
 *
 * Exposes window.SI with helper functions consumed by the other SI modules.
 */
(function() {
  'use strict';

  function csrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (el) return el.value;
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  function api(url, opts) {
    opts = opts || {};
    opts.credentials = 'same-origin';
    opts.headers = Object.assign({'X-Requested-With': 'XMLHttpRequest'}, opts.headers || {});
    if (opts.json) {
      opts.body = JSON.stringify(opts.json);
      opts.headers['Content-Type'] = 'application/json';
      opts.method = opts.method || 'POST';
      delete opts.json;
    }
    if (opts.method === 'POST' || opts.method === 'DELETE') {
      opts.headers['X-CSRFToken'] = csrfToken();
    }
    return fetch(url, opts).then(function(r) { return r.json(); });
  }

  function escapeHtml(str) {
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  function formatMarkdown(text) {
    if (typeof marked !== 'undefined' && marked.parse) {
      return marked.parse(text);
    }
    return '<p>' + escapeHtml(text).replace(/\n/g, '<br>') + '</p>';
  }

  window.SI = window.SI || {};
  SI.csrfToken = csrfToken;
  SI.api = api;
  SI.escapeHtml = escapeHtml;
  SI.formatMarkdown = formatMarkdown;
})();

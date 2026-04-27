(function() {
  'use strict';

  function csrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (el) return el.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
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
    return fetch(url, opts).then(function(response) { return response.json(); });
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function formatMarkdown(text) {
    if (typeof marked !== 'undefined' && marked.parse) return marked.parse(text);
    return '<p>' + escapeHtml(text).replace(/\n/g, '<br>') + '</p>';
  }

  function formatMarkdownInline(text) {
    if (typeof marked !== 'undefined' && marked.parseInline) return marked.parseInline(text);
    return escapeHtml(text);
  }

  window.SI = window.SI || {};
  SI.csrfToken = csrfToken;
  SI.api = api;
  SI.escapeHtml = escapeHtml;
  SI.formatMarkdown = formatMarkdown;
  SI.formatMarkdownInline = formatMarkdownInline;
})();

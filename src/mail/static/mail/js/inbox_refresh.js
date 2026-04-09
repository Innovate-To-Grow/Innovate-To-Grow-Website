(function () {
  'use strict';

  function closest(el, selector) {
    if (!el || !el.closest) return null;
    return el.closest(selector);
  }

  document.body.addEventListener('click', function (e) {
    var btn = closest(e.target, '[data-inbox-refresh]');
    if (!btn) return;
    e.preventDefault();

    var root = closest(btn, '#inbox-all-dynamic');
    if (!root) return;

    var url = root.getAttribute('data-fragment-url');
    if (!url) return;

    btn.classList.add('i2g-inbox-refresh--loading');
    btn.setAttribute('disabled', 'disabled');

    fetch(url, {
      credentials: 'same-origin',
      headers: {'X-Requested-With': 'XMLHttpRequest'},
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Request failed');
        return r.text();
      })
      .then(function (html) {
        root.innerHTML = html;
      })
      .catch(function () {
        window.alert('Could not refresh inbox. Please try again.');
      })
      .finally(function () {
        btn.classList.remove('i2g-inbox-refresh--loading');
        btn.removeAttribute('disabled');
      });
  });
})();

/*
 * i2g-embed.js — makes an archived event page behave well when it is embedded
 * in an <iframe> by the main I2G site's CMS "Embed (iframe)" block.
 *
 * It is a no-op when the page is opened directly (not inside a frame), so the
 * standalone archive site is unaffected.
 *
 * When framed it does three things, all on this (the embedded) side — the only
 * side that can, since the parent CMS page is cross-origin and cannot reach in:
 *
 *   1. Reports this document's full content height to the parent via
 *      postMessage({type:'i2g-embed-resize', height}) on every size change, so
 *      the parent can grow the iframe to fit and no inner scrollbar is needed.
 *   2. Suppresses this page's own scrollbars (the parent frame is the only
 *      scroll surface the visitor should see).
 *   3. Opens real navigation links in a new tab, so a click never strands the
 *      visitor inside the chromeless framed view.
 *
 * Protocol note: the message shape ({type, height}) matches the existing
 * `i2g-embed-resize` contract the CMS already uses for same-origin widgets.
 * The target origin is '*' deliberately — the payload is non-sensitive (just a
 * height), and the parent verifies event.origin/event.source on its end.
 */
(function () {
  'use strict';

  // Only act when actually embedded. window.top can throw on exotic cross-origin
  // nesting, so guard defensively and fall back to "not embedded".
  var framed;
  try {
    framed = window.parent !== window;
  } catch (e) {
    framed = false;
  }
  if (!framed) return;

  var MESSAGE_TYPE = 'i2g-embed-resize';
  var lastHeight = -1;

  function currentHeight() {
    var doc = document.documentElement;
    var body = document.body;
    // Full content height: the tallest of the document/body scroll & offset
    // heights. overflow:hidden (below) does NOT shrink scrollHeight, so this
    // still reflects the real content even after we kill the scrollbar.
    return Math.max(
      doc ? doc.scrollHeight : 0,
      doc ? doc.offsetHeight : 0,
      body ? body.scrollHeight : 0,
      body ? body.offsetHeight : 0
    );
  }

  function reportHeight() {
    var height = currentHeight();
    if (height <= 0 || height === lastHeight) return;
    lastHeight = height;
    try {
      window.parent.postMessage({ type: MESSAGE_TYPE, height: height }, '*');
    } catch (e) {
      /* parent gone or blocked — nothing we can do */
    }
  }

  // Kill this page's own scrollbars; the parent iframe scrolls/sizes instead.
  function suppressOwnScroll() {
    var style = document.createElement('style');
    style.id = 'i2g-embed-style';
    style.textContent =
      'html, body { overflow: hidden !important; margin: 0 !important; }';
    (document.head || document.documentElement).appendChild(style);
  }

  // Real navigation links should pop out of the frame. Use event delegation so
  // it keeps working for rows DataTables re-renders, and skip in-page controls
  // (anchors with no destination, hash-only, or javascript: handlers).
  function openLinksInNewTab() {
    document.addEventListener(
      'click',
      function (event) {
        var node = event.target;
        while (node && node.nodeName !== 'A') {
          node = node.parentNode;
        }
        if (!node || node.nodeName !== 'A') return;
        var href = node.getAttribute('href');
        if (!href) return;
        var lowered = href.trim().toLowerCase();
        if (lowered === '' || lowered.charAt(0) === '#') return;
        if (lowered.indexOf('javascript:') === 0) return;
        node.setAttribute('target', '_blank');
        node.setAttribute('rel', 'noopener noreferrer');
      },
      true // capture: set target before the browser acts on the click
    );
  }

  function init() {
    suppressOwnScroll();
    openLinksInNewTab();
    reportHeight();

    if (typeof ResizeObserver !== 'undefined') {
      var ro = new ResizeObserver(reportHeight);
      ro.observe(document.documentElement);
      if (document.body) ro.observe(document.body);
    } else {
      // Old browsers: poll as a fallback so late-loading tables still resize.
      window.setInterval(reportHeight, 500);
    }

    // The archive tables fill in asynchronously (Sheets proxy + DataTables),
    // so re-measure after load and shortly after in case layout settles late.
    window.addEventListener('load', reportHeight);
    window.setTimeout(reportHeight, 300);
    window.setTimeout(reportHeight, 1200);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

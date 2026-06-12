/**
 * Shared escaping helpers for archived event pages that render Google Sheets
 * data fetched through the /api/sheets/ proxy.
 *
 * Sheet cells cross a trust boundary (anyone with edit/share access to the I2G
 * spreadsheets can set them), so they must never be injected as raw HTML or
 * used as an unchecked link target. Loaded from base.html before any event
 * script so every page can rely on these globals.
 *
 * `escapeSheetText`  -> HTML-escape a cell for safe string concatenation.
 * `prependSheetText` -> prepend a cell as a text node (never parsed as HTML).
 * `safeSheetUrl`     -> return the URL only if it is http(s), else null.
 *
 * Guarded with `typeof` so a page that ships its own copy keeps its version.
 */
if (typeof escapeSheetText === "undefined") {
  function escapeSheetText(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
}

if (typeof prependSheetText === "undefined") {
  function prependSheetText(selector, value) {
    var text = String(value == null ? "" : value);
    var nodes = document.querySelectorAll(selector);
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].insertBefore(document.createTextNode(text), nodes[i].firstChild);
    }
  }
}

if (typeof safeSheetUrl === "undefined") {
  function safeSheetUrl(value) {
    if (!value) {
      return null;
    }
    try {
      var url = new URL(value, window.location.origin);
      if (url.protocol === "http:" || url.protocol === "https:") {
        return url.href;
      }
    } catch (e) {
      return null;
    }
    return null;
  }
}

from django.utils.html import escape as html_escape

from miniapps.models import MiniApp

ITG_SDK_SOURCE = """
(function() {
  'use strict';

  var pendingRequests = {};

  function generateId() {
    return 'req_' + Math.random().toString(36).substr(2, 12) + '_' + Date.now();
  }

  function sendRequest(action, params) {
    return new Promise(function(resolve, reject) {
      var id = generateId();
      pendingRequests[id] = { resolve: resolve, reject: reject };
      window.parent.postMessage({
        type: 'itg-miniapp-request',
        id: id,
        action: action,
        params: params || {}
      }, '*');
    });
  }

  window.addEventListener('message', function(event) {
    var data = event.data;
    if (!data || data.type !== 'itg-miniapp-response') return;
    var pending = pendingRequests[data.id];
    if (!pending) return;
    delete pendingRequests[data.id];
    if (data.error) {
      pending.reject(new Error(data.error));
    } else {
      pending.resolve(data.data);
    }
  });

  function autoResize() {
    var height = document.documentElement.scrollHeight;
    window.parent.postMessage({
      type: 'itg-miniapp-resize',
      height: height
    }, '*');
  }

  var resizeObserver = new ResizeObserver(function() { autoResize(); });
  document.addEventListener('DOMContentLoaded', function() {
    resizeObserver.observe(document.body);
    autoResize();
  });

  window.ITG = {
    api: {
      list: function(params) { return sendRequest('api.list', params); },
      get: function(id) { return sendRequest('api.get', { id: id }); },
      create: function(data) { return sendRequest('api.create', { data: data }); },
      update: function(id, data) { return sendRequest('api.update', { id: id, data: data }); },
      delete: function(id) { return sendRequest('api.delete', { id: id }); }
    },
    fetch: function(url, options) { return sendRequest('fetch', { url: url, options: options }); },
    auth: {
      getUser: function() { return sendRequest('auth.getUser'); }
    },
    navigate: function(path) {
      window.parent.postMessage({
        type: 'itg-miniapp-request',
        id: generateId(),
        action: 'navigate',
        params: { path: path }
      }, '*');
    },
    resize: autoResize
  };
})();
"""


def _escape_for_script(code: str) -> str:
    """Escape </ sequences to prevent premature script/style tag closure."""
    return code.replace("</", r"<\/")


def _escape_for_style(code: str) -> str:
    """Escape </style> in CSS to prevent premature style tag closure."""
    return code.replace("</style>", r"<\/style>").replace("</STYLE>", r"<\/STYLE>")


def _escape_json_string(s: str) -> str:
    """Escape a string for safe embedding in a JSON string literal inside a script tag."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("</", "<\\/")


def render_miniapp_document(app: MiniApp, current_path: str = "") -> str:
    """Build the full HTML document served to the sandbox iframe."""
    safe_css = _escape_for_style(app.css_code)
    safe_js = _escape_for_script(app.js_code)
    safe_path = _escape_json_string(current_path or app.url_path)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'unsafe-inline'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src * data: blob:; connect-src 'none'; frame-src 'none'; object-src 'none'; worker-src 'none';">
<title>{html_escape(app.title)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.5; }}
{safe_css}
</style>
</head>
<body>
{app.html_code}
<script>window.__ITG_PATH = "{safe_path}";</script>
<script>{ITG_SDK_SOURCE}</script>
<script>
{safe_js}
</script>
</body>
</html>"""

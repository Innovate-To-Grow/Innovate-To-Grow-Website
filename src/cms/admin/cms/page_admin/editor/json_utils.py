"""JSON helpers for safely inlining editor configuration."""

import json

_JSON_SCRIPT_ESCAPES = {
    ord("<"): "\\u003C",
    ord(">"): "\\u003E",
    ord("&"): "\\u0026",
    0x2028: "\\u2028",
    0x2029: "\\u2029",
}


def _safe_json(value, **kwargs):
    return json.dumps(value, **kwargs).translate(_JSON_SCRIPT_ESCAPES)

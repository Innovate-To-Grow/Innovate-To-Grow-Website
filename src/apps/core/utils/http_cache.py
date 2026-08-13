import hashlib
import json

from django.http import HttpResponseNotModified
from rest_framework.response import Response

PUBLIC_JSON_MAX_AGE = 60
PUBLIC_JSON_STALE_WHILE_REVALIDATE = 300


def _canonical_json_etag(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return f'"{hashlib.sha256(payload).hexdigest()}"'


def _etag_matches(if_none_match, etag):
    if not if_none_match:
        return False
    for candidate in if_none_match.split(","):
        candidate = candidate.strip()
        if candidate == "*":
            return True
        if candidate.startswith("W/"):
            candidate = candidate[2:].strip()
        if candidate == etag:
            return True
    return False


def public_json_response(
    request,
    data,
    *,
    etag_data=None,
    max_age=PUBLIC_JSON_MAX_AGE,
    stale_while_revalidate=PUBLIC_JSON_STALE_WHILE_REVALIDATE,
):
    """Return stable conditional-GET headers for a public JSON representation."""
    etag = _canonical_json_etag(data if etag_data is None else etag_data)
    if _etag_matches(request.headers.get("If-None-Match"), etag):
        response = HttpResponseNotModified()
    else:
        response = Response(data)
    response["ETag"] = etag
    response["Cache-Control"] = f"public, max-age={max_age}, stale-while-revalidate={stale_while_revalidate}"
    return response

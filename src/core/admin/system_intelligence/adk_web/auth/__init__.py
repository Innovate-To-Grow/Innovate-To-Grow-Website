"""Authentication middleware for the admin ADK web app."""

from .middleware import AdminADKWebAuthMiddleware
from .responses import _is_browser_shell_path, _send_plain_response, _send_redirect_to_admin_login
from .rewrite import (
    _RUN_BODY_PATHS,
    _USER_PATH_RE,
    _read_body,
    _replace_content_length,
    _rewrite_json_body_user_id,
    _rewrite_query_user_id,
    _rewrite_scope_user_id,
    _rewrite_user_path,
)
from .session import _load_staff_user_id_from_headers_sync, _session_key_from_headers, load_staff_user_id_from_headers

__all__ = [
    "AdminADKWebAuthMiddleware",
    "_rewrite_user_path",
    "load_staff_user_id_from_headers",
]

from __future__ import annotations

import ast

from .template import DJANGO_POLICY_PATH, NGINX_SERVER_PATH, NGINX_UWSGI_PATH, require


def _policy_string_set(name: str) -> set[str]:
    tree = ast.parse(DJANGO_POLICY_PATH.read_text(encoding="utf-8"), filename=str(DJANGO_POLICY_PATH))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            value = ast.literal_eval(node.value)
            require(isinstance(value, set), f"{name} must remain a literal set so infrastructure CI can audit it")
            return {str(item).lower() for item in value}
    raise AssertionError(f"missing Django policy set {name}")


def _nginx_alternatives_after_marker(server_config: str, marker: str, prefix: str = "/") -> set[str]:
    lines = server_config.splitlines()
    marker_index = next((index for index, line in enumerate(lines) if line.strip() == f"# {marker}"), None)
    require(marker_index is not None, f"missing Nginx policy marker {marker}")
    location = next((line.strip() for line in lines[marker_index + 1 :] if line.strip()), "")
    require("(?:" in location, f"{marker} must be followed by an alternation location")
    alternatives = location.split("(?:", 1)[1].split(")", 1)[0].split("|")
    require(all(alternatives), f"{marker} contains an empty path alternative")
    return {f"{prefix}{item}".lower() for item in alternatives}


def _validate_private_server(server_config: str) -> None:
    for required in (
        "listen 172.31.69.63:8080;",
        "server 127.0.0.1:5001;",
        "allow 10.2.0.0/16;",
        "deny all;",
        "GET  1;",
        "HEAD 1;",
        "return 405;",
        "return 404;",
        "access_log /var/log/nginx/i2g-legacy-private-access.log i2g_legacy_private;",
    ):
        require(required in server_config, f"private Nginx config is missing {required}")

    log_format = server_config.split("log_format i2g_legacy_private", 1)[1].split(";", 1)[0]
    require("$request_method" in log_format and "$uri" in log_format, "private log needs method and path")
    log_format_names = log_format.replace("$request_method", "").replace("$request_time", "")
    require("$request" not in log_format_names, "private log must not record raw requests")
    require("$args" not in log_format, "private log must not record query strings")
    error_logs = [line.strip() for line in server_config.splitlines() if line.strip().startswith("error_log ")]
    require(
        error_logs == ["error_log /dev/null error;"],
        "private Nginx error log must not record request lines or query strings",
    )


def _validate_uwsgi_snippet(uwsgi_config: str) -> None:
    for required in (
        "uwsgi_pass i2g_legacy_application;",
        'uwsgi_param HTTP_AUTHORIZATION "";',
        'uwsgi_param HTTP_COOKIE "";',
        "uwsgi_hide_header Set-Cookie;",
    ):
        require(required in uwsgi_config, f"uWSGI snippet is missing {required}")


def _validate_route_parity(server_config: str) -> None:
    """The Nginx route lists must match the Django policy exactly."""
    information = _nginx_alternatives_after_marker(server_config, "I2G_LEGACY_INFORMATION_PATHS")
    require(
        information == _policy_string_set("_INFORMATION_PATHS") - {"/"},
        "Nginx information routes must exactly match the Django positive allowlist",
    )
    apis = _nginx_alternatives_after_marker(server_config, "I2G_LEGACY_READ_ONLY_API_PATHS", "/api/")
    require(apis == _policy_string_set("_READ_ONLY_API_PATHS"), "Nginx read-only APIs must match Django")
    blocked = _nginx_alternatives_after_marker(server_config, "I2G_LEGACY_BLOCKED_PREFIXES")
    require(blocked == _policy_string_set("_BLOCKED_PREFIXES"), "Nginx blocked prefixes must match Django")

    blocked_static = _nginx_alternatives_after_marker(
        server_config,
        "I2G_LEGACY_BLOCKED_STATIC_PATHS",
        "/static/",
    )
    blocked_static = {path.replace(r"\.", ".") for path in blocked_static}
    require(blocked_static == _policy_string_set("_BLOCKED_STATIC_PATHS"), "Nginx blocked static paths must match")
    require("location ~* ^/event/" in server_config, "Nginx must block Flask-Admin /event descendants")
    require("location ~* ^/static/admin(?:/|$)" in server_config, "Nginx must block Flask-Admin static assets")
    require("location ~* ^/static/.+" in server_config, "reviewed pages require their non-admin static assets")
    require("location = /" in server_config, "the audited information root must be allowed explicitly")
    require("^/past-projects/[0-9a-f]{8}" in server_config, "the audited UUID detail route is missing")


def validate_nginx_policy() -> None:
    server_config = NGINX_SERVER_PATH.read_text(encoding="utf-8")
    uwsgi_config = NGINX_UWSGI_PATH.read_text(encoding="utf-8")
    _validate_private_server(server_config)
    _validate_uwsgi_snippet(uwsgi_config)
    _validate_route_parity(server_config)

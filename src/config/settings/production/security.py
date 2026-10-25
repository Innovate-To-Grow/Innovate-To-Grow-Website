"""HTTP, cookie, proxy, CORS/CSRF, and CSP settings for production."""

from django.core.exceptions import ImproperlyConfigured

from .env import _get_bool_env, _get_int_env, _split_csv_env

# Security hardening
REQUIRE_ENCRYPTED_PASSWORDS = True

# HTTP security headers
SECURE_SERVER_HEADER = None  # Do not expose server software
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevent MIME-type sniffing
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True  # Defense-in-depth; ALB already redirects, but enforce at the app layer too.

# Trusted reverse-proxy hops in front of uvicorn (one ALB = 1). ``X-Forwarded-For`` is client-supplied
# except for the entries our own proxies append, so the Nth entry from the right is the real client.
# This top-level value serves the app's own helpers (``apps.core.utils.client_ip`` etc.); DRF throttling
# reads ``REST_FRAMEWORK["NUM_PROXIES"]`` instead, which ``environments/production.py`` sets from this value.
# A value below 1 would key every throttle on the ALB's own address, i.e. one global bucket.
NUM_PROXIES = _get_int_env("NUM_PROXIES", 1)
if NUM_PROXIES < 1:
    raise ImproperlyConfigured("NUM_PROXIES must be at least 1 in production (the ALB is a trusted proxy hop).")

# Cookie security
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_AGE = 28800  # 8-hour admin sessions (default was 2 weeks)

# CORS / CSRF trusted origins (comma-separated env vars)
CSRF_TRUSTED_ORIGINS = _split_csv_env("CSRF_TRUSTED_ORIGINS")
CORS_ALLOWED_ORIGINS = _split_csv_env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# Validate CORS_ALLOWED_ORIGINS when credentials are enabled
if CORS_ALLOW_CREDENTIALS and CORS_ALLOWED_ORIGINS:
    for _origin in CORS_ALLOWED_ORIGINS:
        _origin = _origin.strip()
        if _origin == "*" or not _origin.startswith(("http://", "https://")):
            raise ImproperlyConfigured(
                f"CORS_ALLOWED_ORIGINS contains invalid origin '{_origin}'. "
                "When CORS_ALLOW_CREDENTIALS=True, only specific http(s):// origins are allowed."
            )

# CSP starts in report-only mode. Promotion is an explicit configuration
# change after the documented seven-day observation window.
CSP_REPORT_ONLY = _get_bool_env("CSP_REPORT_ONLY", True)
CSP_REPORT_RATE_LIMIT = _get_int_env("CSP_REPORT_RATE_LIMIT", 60)
CSP_REPORT_RATE_WINDOW_SECONDS = _get_int_env("CSP_REPORT_RATE_WINDOW_SECONDS", 60)
CSP_SCRIPT_SOURCES = (
    "'self'",
    "https://cdn.jsdelivr.net",
)
CSP_STYLE_SOURCES = ("'self'", "https://fonts.googleapis.com")
CSP_FONT_SOURCES = ("'self'", "data:", "https://fonts.gstatic.com")
CSP_IMAGE_SOURCES = ("'self'", "data:", "blob:")
CSP_CONNECT_SOURCES = (
    "'self'",
    "https://fonts.googleapis.com",
    "https://fonts.gstatic.com",
)

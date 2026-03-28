# Settings package
#
# Structure:
#   base.py        – Assembles all component fragments into one importable module.
#   dev.py         – Development overrides (SQLite, DEBUG=True, insecure key).
#   prod.py        – Production overrides (imports components/production.py).
#   ci.py          – CI pipeline overrides (PostgreSQL test database).
#
#   components/
#     framework/
#       environment.py  – BASE_DIR, .env loading, shared env vars (SES, URLs, i18n).
#       django.py       – INSTALLED_APPS, middleware, templates, auth, static/media.
#     integrations/
#       api.py          – DRF and SimpleJWT configuration.
#       admin.py        – Unfold admin theme, sidebar navigation, branding.
#       editor.py       – CKEditor 5 toolbar and plugin configuration.
#     production.py     – Production-only security, S3 storage, logging, caching.

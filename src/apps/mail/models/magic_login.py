"""Legacy import shim — kept so landed migrations stay importable.

``mail/migrations/0001_initial.py`` references ``mail.models.magic_login.default_expiry``
(resolved through the ``_legacy_imports`` meta-path alias). Do not delete this module;
new code must import from :mod:`apps.mail.models.login_link` instead.
"""

from .login_link import LoginLinkToken, default_expiry  # noqa: F401

# Old model name, for any straggling external references.
MagicLoginToken = LoginLinkToken

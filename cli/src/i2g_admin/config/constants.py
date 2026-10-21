"""Shared constants for the i2g-admin configuration package."""

import re

# Profile names become filename suffixes (credentials-<name>.json); restrict them
# to a safe character set so a name can never escape the config dir or surprise
# the filesystem (e.g. "../../x", "a/b").
_PROFILE_NAME_RE = re.compile(r"\A[A-Za-z0-9._-]+\Z")

APP_DIR_NAME = "i2g-admin"
CREDENTIALS_FILE = "credentials.json"
CONFIG_FILE = "config.json"
DOTENV_FILE = ".env"
# Name of the environment variable (and .env key) that holds the backend base URL.
# The value itself is intentionally NOT hardcoded here: the deployment target
# lives in the environment or a .env file (see cli/.env.example), never in source.
ENV_BASE_URL = "I2G_ADMIN_BASE_URL"
# Name of the environment variable that selects the active named profile.
ENV_PROFILE = "I2G_ADMIN_PROFILE"
DOTENV_ALLOWED_KEYS = frozenset({ENV_BASE_URL, ENV_PROFILE})
DEFAULT_PROFILE = "default"
# http is only permitted to literal loopback hosts (local dev); everything else
# must be https so the bearer token is never sent in cleartext to a remote host.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

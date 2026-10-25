"""Configuration: profiles, credentials, dotenv, and base-URL resolution.

The implementation is split into focused submodules; this package ``__init__``
re-exports the public API so callers keep using ``config.<name>``. The submodules
call each other directly (``credentials.load_credentials``, ``store._read_json``),
so a name can have two lookup paths: patch it on the module the caller looks it
up on — the submodule for calls made inside this package, ``config.<name>`` for
callers outside it.
"""

from .constants import (  # noqa: F401
    APP_DIR_NAME,
    CONFIG_FILE,
    CREDENTIALS_FILE,
    DEFAULT_PROFILE,
    DOTENV_ALLOWED_KEYS,
    DOTENV_FILE,
    ENV_BASE_URL,
    ENV_PROFILE,
    LOOPBACK_HOSTS,
)
from .credentials import (  # noqa: F401
    clear_credentials,
    credentials_path,
    load_credentials,
    save_credentials,
)
from .dotenv import load_dotenv  # noqa: F401
from .profiles import default_profile, list_profiles, resolve_profile  # noqa: F401
from .store import config_dir  # noqa: F401
from .urls import (  # noqa: F401
    configured_base_url,
    current_base_url,
    default_base_url,
    set_base_url,
    validate_base_url,
)

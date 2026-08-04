"""Container-build settings for deterministic static asset collection.

This module deliberately uses the local filesystem and SQLite: image builds
must not need production database or S3 credentials. Unlike local development,
its staticfiles backend emits content-hashed names and ``staticfiles.json`` so
the image itself is the source of the immutable S3 rollout.
"""

import os
from pathlib import Path

from .local import *  # noqa: F403

DEBUG = False
STATIC_ROOT = Path(os.environ.get("BUILD_STATIC_ROOT", BASE_DIR / "static"))  # noqa: F405
# local.py intentionally includes frontend development assets and explicitly
# repeats apps/core/static. The app finder already discovers the latter, and
# the backend Docker build context does not contain pages/, so retain only
# existing non-app directories.
_APP_STATIC_ROOT = BASE_DIR / "apps" / "core" / "static"  # noqa: F405
STATICFILES_DIRS = [  # noqa: F405
    path
    for path in dict.fromkeys(STATICFILES_DIRS)  # noqa: F405
    if Path(path).is_dir() and Path(path) != _APP_STATIC_ROOT
]
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}

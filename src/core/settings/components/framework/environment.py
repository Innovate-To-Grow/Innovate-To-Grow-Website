"""
Environment bootstrap and shared constants.

Loaded first by ``base.py`` so that every other component can reference
BASE_DIR and environment variables.  Values here come from ``src/.env``
(via python-dotenv) or from the process environment.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# BASE_DIR points to the ``src/`` directory (four parents up from this file).
# framework/environment.py → framework/ → components/ → settings/ → core/ → src/
BASE_DIR = Path(__file__).resolve().parents[4]

load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Application URLs (set per environment; empty defaults are overridden in
# dev.py / prod.py as needed)
# ---------------------------------------------------------------------------
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "")

# ---------------------------------------------------------------------------
# AWS SES email credentials and defaults
# ---------------------------------------------------------------------------
SES_AWS_ACCESS_KEY_ID = os.environ.get("SES_AWS_ACCESS_KEY_ID", "")
SES_AWS_SECRET_ACCESS_KEY = os.environ.get("SES_AWS_SECRET_ACCESS_KEY", "")
SES_AWS_REGION = os.environ.get("SES_AWS_REGION", "us-west-2")
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "i2g@g.ucmerced.edu")
SES_FROM_NAME = os.environ.get("SES_FROM_NAME", "Innovate to Grow")
SES_CONFIGURATION_SET_NAME = os.environ.get("SES_CONFIGURATION_SET_NAME", "")
SES_SNS_TOPIC_ARN = os.environ.get("SES_SNS_TOPIC_ARN", "")

# ---------------------------------------------------------------------------
# Internationalization / timezone
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"
USE_I18N = True
USE_TZ = True

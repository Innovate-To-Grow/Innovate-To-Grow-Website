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
# framework/environment.py → framework/ → components/ → settings/ → config/ → src/
BASE_DIR = Path(__file__).resolve().parents[4]

load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Application URLs (set per environment; empty defaults are overridden in
# local.py / production.py as needed)
# ---------------------------------------------------------------------------
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "")

# ---------------------------------------------------------------------------
# AWS SES optional features (env-only; SES credentials live in EmailServiceConfig)
# ---------------------------------------------------------------------------
SES_CONFIGURATION_SET_NAME = os.environ.get("SES_CONFIGURATION_SET_NAME", "")
SES_SNS_TOPIC_ARN = os.environ.get("SES_SNS_TOPIC_ARN", "")

# Route redirects are reconciled with Amplify through the ECS task role's
# ambient boto3 credentials.  The app ID is optional so local installations
# retain the SPA fallback without attempting provider I/O.
AWS_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_S3_REGION_NAME", "us-west-2")).strip()
AMPLIFY_APP_ID = os.environ.get("AMPLIFY_APP_ID", "").strip()
AMPLIFY_BACKEND_PROXY_URL = os.environ.get("AMPLIFY_BACKEND_PROXY_URL", "").strip().rstrip("/")
AMPLIFY_PROXY_ADMIN_PATHS = os.environ.get("AMPLIFY_PROXY_ADMIN_PATHS", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
AMPLIFY_CONFIG_REVISION = os.environ.get("AMPLIFY_CONFIG_REVISION", "").strip()

# Durable PostgreSQL outbox rollout. Deploy schema + worker with this false,
# verify the worker heartbeat, then set true on web tasks to begin queueing.
BACKGROUND_JOBS_ENABLED = os.environ.get("BACKGROUND_JOBS_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
}
BACKGROUND_JOB_METRICS_NAMESPACE = os.environ.get(
    "BACKGROUND_JOB_METRICS_NAMESPACE",
    "",
).strip()

# ---------------------------------------------------------------------------
# Internationalization / timezone
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"
USE_I18N = True
USE_TZ = True

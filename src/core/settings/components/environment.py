"""Environment and shared constants for Django settings."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]

load_dotenv(BASE_DIR / ".env")

FRONTEND_URL = os.environ.get("FRONTEND_URL", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "")

SES_AWS_ACCESS_KEY_ID = os.environ.get("SES_AWS_ACCESS_KEY_ID", "")
SES_AWS_SECRET_ACCESS_KEY = os.environ.get("SES_AWS_SECRET_ACCESS_KEY", "")
SES_AWS_REGION = os.environ.get("SES_AWS_REGION", "us-west-2")
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "i2g@g.ucmerced.edu")
SES_FROM_NAME = os.environ.get("SES_FROM_NAME", "Innovate to Grow")
SES_CONFIGURATION_SET_NAME = os.environ.get("SES_CONFIGURATION_SET_NAME", "")
SES_SNS_TOPIC_ARN = os.environ.get("SES_SNS_TOPIC_ARN", "")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"
USE_I18N = True
USE_TZ = True

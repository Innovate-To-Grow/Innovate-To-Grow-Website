"""S3 storage and static/media settings for production."""

import os

from ..base.framework.environment import BASE_DIR
from .env import _get_required_env

# AWS S3 storage (static files and media uploads)
AWS_STORAGE_BUCKET_NAME = _get_required_env("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-west-2")
AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN", f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com")
AWS_DEFAULT_ACL = None  # Inherit bucket policy
AWS_S3_FILE_OVERWRITE = False  # Never silently overwrite uploads
AWS_QUERYSTRING_AUTH = False  # Public URLs (no signed query strings)
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}  # 1-day browser cache

STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/media/"

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "region_name": AWS_S3_REGION_NAME,
            "location": "media",
            "file_overwrite": False,
            "querystring_auth": False,
            "default_acl": None,
            "object_parameters": AWS_S3_OBJECT_PARAMETERS,
        },
    },
    "staticfiles": {
        "BACKEND": "storages.backends.s3boto3.S3StaticStorage",
        "OPTIONS": {
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "region_name": AWS_S3_REGION_NAME,
            "location": "static",
            # Static assets are release artifacts. They must replace older
            # files with the same path so non-hashed admin JS/CSS updates go live.
            "file_overwrite": True,
            "querystring_auth": False,
            "default_acl": None,
            "object_parameters": AWS_S3_OBJECT_PARAMETERS,
        },
    },
}

"""
Django base settings for core project.

This file contains settings that are common to all environments.
"""

import os
from datetime import timedelta
from pathlib import Path

from django.templatetags.static import static
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")

# Frontend URL for Live Preview (optional)
# If set, the "Open Live Preview" button in admin will link to this URL + /preview
# Example: "https://www.innovatetogrow.com" or "http://localhost:5173"
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "")

# SES admin sender configuration
SES_AWS_ACCESS_KEY_ID = os.environ.get("SES_AWS_ACCESS_KEY_ID", "")
SES_AWS_SECRET_ACCESS_KEY = os.environ.get("SES_AWS_SECRET_ACCESS_KEY", "")
SES_AWS_REGION = os.environ.get("SES_AWS_REGION", "us-west-2")
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "i2g@g.ucmerced.edu")
SES_FROM_NAME = os.environ.get("SES_FROM_NAME", "Innovate to Grow")
SES_CONFIGURATION_SET_NAME = os.environ.get("SES_CONFIGURATION_SET_NAME", "")
SES_SNS_TOPIC_ARN = os.environ.get("SES_SNS_TOPIC_ARN", "")

# Google Sheets settings
# Preferred: service account credentials (production)
GOOGLE_SHEETS_CREDENTIALS_JSON = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
GOOGLE_SHEETS_SCOPES = [
    scope.strip()
    for scope in os.environ.get(
        "GOOGLE_SHEETS_SCOPES",
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ).split(",")
    if scope.strip()
]
# Fallback: API key for public read-only access (dev)
GOOGLE_SHEETS_API_KEY = os.environ.get("GOOGLE_SHEETS_API_KEY", "")

# Application definition
INSTALLED_APPS = [
    # Admin theme (must be before django.contrib.admin)
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    # django contrib application
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # applications
    "core.apps.CoreConfig",
    "pages.apps.PagesConfig",
    "authn.apps.AuthnConfig",
    "event.apps.EventConfig",
    "news.apps.NewsConfig",
    "projects.apps.ProjectsConfig",
    "mail.apps.MailConfig",
    "analytics.apps.AnalyticsConfig",
    # third party application
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_ckeditor_5",
]

MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",
    # Must run before middlewares that may short-circuit responses (e.g. /health/)
    # so CORS headers are always added for allowed origins.
    "corsheaders.middleware.CorsMiddleware",
    "core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "core" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "America/Los_Angeles"

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"

STATICFILES_DIRS = [
    BASE_DIR / "core" / "static",
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# File Storage Configuration
# --------------------------
# By default, Django uses local filesystem storage.
# For production with cloud storage (S3, R2, etc.), configure in prod.py
#
# Storage backends available:
# - django.core.files.storage.FileSystemStorage (default, local)
# - storages.backends.s3boto3.S3Boto3Storage (AWS S3 / S3-compatible)
#
# The DEFAULT_FILE_STORAGE setting is deprecated in Django 4.2+
# Use STORAGES dict instead for Django 4.2+
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "authn.Member"

# Allow email or username authentication.
AUTHENTICATION_BACKENDS = [
    "authn.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Django REST Framework Configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "login": "10/minute",
        "email_code_request": "10/minute",
        "email_code_verify": "20/minute",
        "past_project_share": "10/minute",
    },
}

# Simple JWT Configuration
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "member_uuid",
}

# CKEditor 5 Configuration
# Used for rich text fields in the admin
CKEDITOR_5_CONFIGS = {
    "default": {
        "toolbar": [
            "heading",
            "|",
            "bold",
            "italic",
            "underline",
            "strikethrough",
            "|",
            "bulletedList",
            "numberedList",
            "blockQuote",
            "|",
            "link",
            "insertImage",
            "mediaEmbed",
            "insertTable",
            "|",
            "sourceEditing",
        ],
        "image": {
            "toolbar": [
                "imageTextAlternative",
                "imageStyle:inline",
                "imageStyle:block",
                "imageStyle:side",
            ],
        },
        "table": {
            "contentToolbar": [
                "tableColumn",
                "tableRow",
                "mergeTableCells",
            ],
        },
        "heading": {
            "options": [
                {"model": "paragraph", "title": "Paragraph", "class": "ck-heading_paragraph"},
                {"model": "heading2", "view": "h2", "title": "Heading 2", "class": "ck-heading_heading2"},
                {"model": "heading3", "view": "h3", "title": "Heading 3", "class": "ck-heading_heading3"},
                {"model": "heading4", "view": "h4", "title": "Heading 4", "class": "ck-heading_heading4"},
            ],
        },
    },
}
CKEDITOR_5_FILE_UPLOAD_PERMISSION = "staff"

# Unfold Admin Theme Configuration
UNFOLD = {
    "SITE_TITLE": "I2G Admin",
    "SITE_HEADER": "Innovate To Grow",
    "SITE_ICON": lambda request: static("images/i2glogo.png"),
    "SITE_LOGO": lambda request: static("images/i2glogo.png"),
    "THEME": "light",  # Force light theme only (disable dark mode)
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": "Site Settings",
                "items": [
                    {"title": "Site Maintenance Control", "link": "/admin/core/sitemaintenancecontrol/"},
                ],
            },
            {
                "title": "Content Management System",
                "items": [
                    {"title": "Home Page", "link": "/admin/pages/sitesettings/"},
                    {"title": "Pages", "link": "/admin/pages/cmspage/"},
                    {"title": "Page Analytics", "link": "/admin/analytics/pageview/"},
                    {"title": "Sheet Sources", "link": "/admin/pages/googlesheetsource/"},
                    {"title": "Menus", "link": "/admin/pages/menu/"},
                    {"title": "Footer", "link": "/admin/pages/footercontent/"},
                ],
            },
            {
                "title": "Events",
                "items": [
                    {"title": "Events", "link": "/admin/event/event/"},
                    {"title": "Registrations", "link": "/admin/event/eventregistration/"},
                ],
            },
            {
                "title": "Projects",
                "items": [
                    {"title": "Semesters", "link": "/admin/projects/semester/"},
                    {"title": "Projects", "link": "/admin/projects/project/"},
                ],
            },
            {
                "title": "Members & Authentication",
                "items": [
                    {"title": "User", "link": "/admin/authn/member/"},
                    {"title": "Contact Emails", "link": "/admin/authn/contactemail/"},
                    {"title": "Members", "link": "/admin/authn/member/"},
                    {"title": "Groups", "link": "/admin/authn/i2gmembergroup/"},
                    {"title": "Admin Invitations", "link": "/admin/authn/admininvitation/"},
                ],
            },
            {
                "title": "News",
                "items": [
                    {"title": "News Articles", "link": "/admin/news/newsarticle/"},
                    {"title": "Feed Sources", "link": "/admin/news/newsfeedsource/"},
                    {"title": "Sync Logs", "link": "/admin/news/newssynclog/"},
                ],
            },
            {
                "title": "Amazon Simple Email Service",
                "items": [
                    {"title": "SES Mail Senders", "link": "/admin/mail/sesaccount/"},
                    {"title": "SES Compose", "link": "/admin/mail/sesaccount/compose/"},
                    {"title": "SES Email Logs", "link": "/admin/mail/sesemaillog/"},
                ],
            },
            {
                "title": "Gmail",
                "items": [
                    {"title": "Gmail API Accounts", "link": "/admin/mail/googleaccount/"},
                    {"title": "Inbox", "link": "/admin/mail/googleaccount/inbox/"},
                    {"title": "Sent Mail", "link": "/admin/mail/googleaccount/sent/"},
                    {"title": "Compose", "link": "/admin/mail/googleaccount/compose/"},
                    {"title": "Email Logs", "link": "/admin/mail/emaillog/"},
                ],
            },
        ],
    },
}

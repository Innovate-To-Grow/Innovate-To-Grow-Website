"""
Django base settings for core project.

This file contains settings that are common to all environments.
"""

from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")


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
    "mobileid.apps.MobileIDConfig",
    "layout.apps.LayoutConfig",
    "notify.apps.NotifyConfig",
    "events.apps.EventsConfig",
    # third party application
    "rest_framework",
    "rest_framework_simplejwt",
    "django_ckeditor_5",
]

MIDDLEWARE = [
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

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "static"

STATICFILES_DIRS = [
    BASE_DIR / "core" / "static",
]

MEDIA_URL = "media/"
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

# Django REST Framework Configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}

# Simple JWT Configuration
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "member_uuid",
    "USER_ID_CLAIM": "member_uuid",
}

# CKEditor 5 Configuration
# Used for rich text fields (not for PageComponent code editing which uses Monaco)
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
    "SITE_SYMBOL": "school",
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": "Content Management",
                "items": [
                    {"title": "Pages", "icon": "article", "link": "/admin/pages/page/"},
                    {"title": "Home Pages", "icon": "home", "link": "/admin/pages/homepage/"},
                    {"title": "Components", "icon": "widgets", "link": "/admin/pages/pagecomponent/"},
                    {"title": "Media", "icon": "image", "link": "/admin/pages/mediaasset/"},
                    {"title": "Forms", "icon": "dynamic_form", "link": "/admin/pages/uniformform/"},
                    {"title": "Submissions", "icon": "inbox", "link": "/admin/pages/formsubmission/"},
                ],
            },
            {
                "title": "Layout",
                "items": [
                    {"title": "Menus", "icon": "menu", "link": "/admin/layout/menu/"},
                    {"title": "Footer", "icon": "bottom_navigation", "link": "/admin/layout/footercontent/"},
                ],
            },
            {
                "title": "Events",
                "items": [
                    {"title": "Events", "icon": "event", "link": "/admin/events/event/"},
                    {"title": "Programs", "icon": "category", "link": "/admin/events/program/"},
                    {"title": "Tracks", "icon": "view_timeline", "link": "/admin/events/track/"},
                ],
            },
            {
                "title": "Members",
                "items": [
                    {"title": "Members", "icon": "people", "link": "/admin/authn/member/"},
                    {"title": "Groups", "icon": "group_work", "link": "/admin/authn/i2gmembergroup/"},
                ],
            },
            {
                "title": "MobileID",
                "items": [
                    {"title": "Barcodes", "icon": "qr_code", "link": "/admin/mobileid/barcode/"},
                    {"title": "Mobile IDs", "icon": "badge", "link": "/admin/mobileid/mobileid/"},
                    {"title": "Transactions", "icon": "receipt_long", "link": "/admin/mobileid/transaction/"},
                ],
            },
            {
                "title": "Email & Notifications",
                "items": [
                    {"title": "Gmail Accounts", "icon": "mail", "link": "/admin/notify/googlegmailaccount/"},
                    {"title": "Email Templates", "icon": "drafts", "link": "/admin/notify/emailmessagelayout/"},
                    {"title": "Email Layouts", "icon": "web", "link": "/admin/notify/emaillayout/"},
                    {"title": "Broadcasts", "icon": "campaign", "link": "/admin/notify/broadcastmessage/"},
                ],
            },
        ],
    },
}

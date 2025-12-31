"""
Django base settings for core project.

This file contains settings that are common to all environments.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')


# Application definition
INSTALLED_APPS = [
    # django contrib application
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # custom application
    "pages.apps.PagesConfig",
    "authn.apps.AuthnConfig",
    "mobileid.apps.MobileIDConfig",
    "layout.apps.LayoutConfig",
    "notify.apps.NotifyConfig",
    "events.apps.EventsConfig",

    # third party application
    "rest_framework",
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

TIME_ZONE = "UTC"

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

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "authn.Member"

# CKEditor 5 Configuration
CKEDITOR_5_CONFIGS = {
    'default': {
        'toolbar': [
            'heading', '|',
            'bold', 'italic', 'underline', 'strikethrough', '|',
            'link', 'blockQuote', 'code', 'codeBlock', '|',
            'bulletedList', 'numberedList', 'todoList', '|',
            'outdent', 'indent', '|',
            'imageUpload', 'insertTable', 'mediaEmbed', '|',
            'undo', 'redo', '|',
            'sourceEditing',
        ],
    },
    'extends': {
        'toolbar': [
            'heading', '|',
            'bold', 'italic', 'underline', 'strikethrough', 'subscript', 'superscript', '|',
            'link', 'blockQuote', 'code', 'codeBlock', '|',
            'bulletedList', 'numberedList', 'todoList', '|',
            'outdent', 'indent', 'alignment', '|',
            'imageUpload', 'insertTable', 'mediaEmbed', '|',
            'fontColor', 'fontBackgroundColor', 'removeFormat', '|',
            'undo', 'redo', '|',
            'sourceEditing',
        ],
        'image': {
            'toolbar': [
                'imageTextAlternative', '|',
                'imageStyle:alignLeft', 'imageStyle:alignCenter', 'imageStyle:alignRight',
            ],
        },
        'table': {
            'contentToolbar': ['tableColumn', 'tableRow', 'mergeTableCells'],
        },
        'heading': {
            'options': [
                {'model': 'paragraph', 'title': 'Paragraph', 'class': 'ck-heading_paragraph'},
                {'model': 'heading1', 'view': 'h1', 'title': 'Heading 1', 'class': 'ck-heading_heading1'},
                {'model': 'heading2', 'view': 'h2', 'title': 'Heading 2', 'class': 'ck-heading_heading2'},
                {'model': 'heading3', 'view': 'h3', 'title': 'Heading 3', 'class': 'ck-heading_heading3'},
            ],
        },
    },
}

# CKEditor 5 file upload settings
CKEDITOR_5_FILE_UPLOAD_PERMISSION = "staff"
CK_EDITOR_5_UPLOAD_FILE_VIEW_NAME = "ck_editor_5_upload_file"

# Events API Key for Google Sheets sync
EVENTS_API_KEY = os.getenv('EVENTS_API_KEY', '')


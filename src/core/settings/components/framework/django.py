"""
Core Django framework configuration.

Defines the fundamental Django settings shared across all environments:
installed apps, middleware stack, templates, authentication, and static/media
file handling.  Environment-specific files (dev/prod/ci) may override values
like DATABASES, STATICFILES_DIRS, or STORAGES.
"""

from .environment import BASE_DIR

# ---------------------------------------------------------------------------
# Installed applications
# ---------------------------------------------------------------------------
# Order matters: Unfold must appear before django.contrib.admin so its
# templates take precedence.  Third-party libs come after project apps.
INSTALLED_APPS = [
    # Admin theme (must precede django.contrib.admin)
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    # authn before django.contrib.auth so our createsuperuser command wins
    "authn.apps.AuthnConfig",
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Project apps
    "core.apps.CoreConfig",
    "cms.apps.CmsConfig",
    "event.apps.EventConfig",
    "projects.apps.ProjectsConfig",
    "mail.apps.MailConfig",
    # Third-party
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # JWT refresh-token blacklisting
    "django_ckeditor_5",
]

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
# GZip and CORS run early; health-check shortcircuits before auth.
MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",
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

# ---------------------------------------------------------------------------
# URL / WSGI
# ---------------------------------------------------------------------------
ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Static and media files (defaults; prod.py overrides with S3)
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
STATICFILES_DIRS = [BASE_DIR / "core" / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# ---------------------------------------------------------------------------
# Upload limits
# ---------------------------------------------------------------------------
# The admin's filter_horizontal widget for selected_members sends one POST
# field per member, easily exceeding Django's default of 1000.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "authn.Member"
AUTHENTICATION_BACKENDS = [
    "authn.backends.EmailAuthBackend",
]

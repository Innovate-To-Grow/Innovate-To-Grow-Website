"""
Core Django framework configuration.

Defines the fundamental Django settings shared across all environments:
installed apps, middleware stack, templates, authentication, and static/media
file handling.  Environment-specific files (local/production/test) may override values
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
    "apps.authn.apps.AuthnConfig",
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Project apps
    "apps.core.apps.CoreConfig",
    "apps.system_intelligence.apps.SystemIntelligenceConfig",
    "apps.cms.apps.CmsConfig",
    "apps.event.apps.EventConfig",
    "apps.projects.apps.ProjectsConfig",
    "apps.mail.apps.MailConfig",
    "apps.cli_admin.apps.CliAdminConfig",
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
# GZip and CORS run early; health-check shortcircuits before auth. The request limiter runs after CORS (so a 429
# carries CORS headers), after the health checks (ALB probes are never limited) and after sessions, and before CSRF
# (its ``process_view`` decides first, so a flood of CSRF failures is limited too; it reads the admin user there,
# after every middleware's request phase); the ``core`` system checks refuse any other order.
MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "apps.core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.core.middleware.RequestRateLimitMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Hosts CMS content may embed in iframes; the CSP middleware allows them as
# frame sources. Each entry is a dotted path to a zero-argument callable.
CSP_FRAME_HOST_PROVIDERS = ("apps.cms.services.sanitization.embed_hosts.get_allowed_hosts",)

# Pages other apps add to /sitemap.xml (served by the CMS). Each entry is a dotted path to a zero-argument callable
# returning (frontend path, last-modified datetime or None) pairs.
SITEMAP_ENTRY_PROVIDERS = ("apps.projects.services.sitemap.archive_project_sitemap_entries",)

# ---------------------------------------------------------------------------
# URL / WSGI
# ---------------------------------------------------------------------------
ROOT_URLCONF = "config.routing.urls"
WSGI_APPLICATION = "config.deploy.wsgi.application"
# ``manage.py test`` only: Django's runner, with the delivery-rate limiter on a virtual clock (see the module).
TEST_RUNNER = "apps.core.tests.runner.ProjectTestRunner"
ASGI_APPLICATION = "config.deploy.asgi.application"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "apps" / "core" / "templates"],
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
# Static and media files (defaults; production.py overrides with S3)
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
# apps/core/static holds first-party admin CSS/JS; assets/vendor holds pinned
# third-party libraries (CodeMirror, Font Awesome, ...) used by the cms and mail
# admin templates. Vendor files live outside any app because no single app owns
# them. Both are collected under STATIC_URL, so `{% static "vendor/..." %}`
# template references are unaffected by which directory a file sits in.
STATICFILES_DIRS = [
    BASE_DIR / "apps" / "core" / "static",
    BASE_DIR / "assets",
]
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
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100000

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "authn.Member"
AUTHENTICATION_BACKENDS = [
    "apps.authn.security.backends.EmailAuthBackend",
]
# Phone sign-in only works for VERIFIED numbers. A number saved on an account but not verified gets a withheld code:
# the same answer as a real send, but no SMS. So that its answer is not quicker than a real one, it waits as long as
# one of this process's recent provider calls took; until the process has sent a code, a time drawn from this
# (low, high) range in seconds, the usual length of one SendTextMessage call (apps/authn/services/sms/latency.py).
SMS_WITHHELD_SEND_DELAY_SECONDS = (0.2, 0.6)

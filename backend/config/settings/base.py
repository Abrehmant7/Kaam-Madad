"""Settings shared by every environment (development, production, test).

Environment-specific modules import ``*`` from here and override what differs.
Configuration comes from environment variables; see ``.env.example`` in the
repository root for every supported variable.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from apps.core.static_cache import is_immutable_asset
from config.env import (
    DEPLOYMENT_MODE_DEMO,
    DEPLOYMENT_MODE_LIVE,
    PHONE_PROVIDER_DEMO,
    PHONE_PROVIDER_UNCONFIGURED,
    env_choice,
    env_int,
    env_list,
    env_str,
)

# backend/ directory and repository root.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BASE_DIR.parent

# Load the repository-root .env for local work. Real environment variables win.
load_dotenv(REPO_ROOT / ".env", override=False)

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
# Each environment module validates or supplies SECRET_KEY.
SECRET_KEY = env_str("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
]

# --------------------------------------------------------------------------
# Deployment mode (NFR-04) and phone verification (AUTH-03)
# --------------------------------------------------------------------------
# "live": real users; simulated authentication is refused at startup.
# "demo": an explicitly separate demonstration deployment; new accounts are
#         flagged is_demo and the UI shows a persistent demo label.
# Each environment module supplies its default and calls check_simulation_allowed().
DEPLOYMENT_MODE = env_choice("APP_DEPLOYMENT_MODE", {DEPLOYMENT_MODE_LIVE, DEPLOYMENT_MODE_DEMO})
# "demo": codes are generated but no SMS is sent; the code is shown on a labelled demo screen.
# "unconfigured": no SMS provider; phone confirmation honestly reports "unavailable".
PHONE_VERIFICATION_PROVIDER = env_choice(
    "PHONE_VERIFICATION_PROVIDER", {PHONE_PROVIDER_DEMO, PHONE_PROVIDER_UNCONFIGURED}
)
PHONE_VERIFICATION_POLICY = {
    "CODE_TTL_SECONDS": 10 * 60,  # a code expires 10 minutes after it is issued
    "MAX_ATTEMPTS": 5,  # wrong entries before the code is invalidated
    "RESEND_COOLDOWN_SECONDS": 60,  # minimum gap between codes
    "MAX_SENDS_PER_HOUR": 5,  # codes per account per rolling hour
}

MIDDLEWARE = [
    # First, so every response (including redirects and errors) carries X-Request-ID.
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Serves the built frontend assets and collected static files (same origin).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Database (PostgreSQL only)
# --------------------------------------------------------------------------
_db_options: dict[str, object] = {
    # Bounds how long a connection attempt (and therefore /health/ready/) can hang.
    "connect_timeout": env_int("POSTGRES_CONNECT_TIMEOUT", 3, minimum=1),
}
if env_str("POSTGRES_SSLMODE"):
    _db_options["sslmode"] = env_str("POSTGRES_SSLMODE")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("POSTGRES_DB", "roshan_rozgaar"),
        "USER": env_str("POSTGRES_USER", "roshan_rozgaar"),
        "PASSWORD": env_str("POSTGRES_PASSWORD"),
        "HOST": env_str("POSTGRES_HOST", "127.0.0.1"),
        "PORT": env_str("POSTGRES_PORT", "5434"),
        "CONN_MAX_AGE": env_int("DJANGO_CONN_MAX_AGE", 0, minimum=0),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": _db_options,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Accounts and authentication
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("phone_number",)},
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Sessions live in PostgreSQL; the session cookie is HttpOnly. SameSite=Lax
# blocks cross-site POSTs carrying the session while allowing navigation.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 14 * 24 * 60 * 60  # 14 days; login rotates the session key
# The SPA reads the CSRF cookie and echoes it in the X-CSRFToken header, so this
# cookie is deliberately readable by JavaScript (it is not a secret on its own).
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_HEADER_NAME = "HTTP_X_CSRFTOKEN"

# Shared cache for rate limiting, stored in PostgreSQL (no Redis). The table
# is created by the core.0001 migration (`createcachetable`).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "app_cache",
    }
}

# --------------------------------------------------------------------------
# Internationalisation and time
# --------------------------------------------------------------------------
# Server/admin language. End-user UI text is translated on the client using
# stable error/status codes (Urdu first, English available).
LANGUAGE_CODE = "en"
LANGUAGES = [("ur", "Urdu"), ("en", "English")]
USE_I18N = True
# Timestamps are stored in UTC (USE_TZ); Asia/Karachi is the display zone.
TIME_ZONE = "Asia/Karachi"
USE_TZ = True

# --------------------------------------------------------------------------
# Static files, built frontend, and private media
# --------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Vite production build. Django serves index.html for client-side routes and
# WhiteNoise serves the hashed assets, so frontend and API share one origin.
FRONTEND_DIST_DIR = Path(env_str("FRONTEND_DIST_DIR") or (REPO_ROOT / "frontend" / "dist"))
WHITENOISE_ROOT = str(FRONTEND_DIST_DIR) if FRONTEND_DIST_DIR.is_dir() else None
WHITENOISE_IMMUTABLE_FILE_TEST = is_immutable_asset

# Private uploads (CNIC images, voice notes, job photos — later modules).
# Deliberately NOT exposed through any URL: downloads must go through
# authorised views (MEDIA-01). Git-ignored.
PRIVATE_MEDIA_ROOT = Path(env_str("PRIVATE_MEDIA_ROOT") or (BASE_DIR / "private_media"))
MEDIA_ROOT = PRIVATE_MEDIA_ROOT

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    # Session auth that also enforces CSRF on anonymous mutations (signup/login)
    # and answers 401 (not 403) when no valid session exists.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.CsrfEnforcedSessionAuthentication",
    ],
    # Client IP for rate limiting = REMOTE_ADDR unless trusted proxies are declared;
    # never trust a client-supplied X-Forwarded-For by default.
    "NUM_PROXIES": env_int("DJANGO_NUM_PROXIES", 0, minimum=0),
    # Deny by default; public endpoints (e.g. health) opt in explicitly.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "apps.core.api.exception_handler.api_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "DEFAULT_PAGINATION_CLASS": "apps.core.api.pagination.StandardPagination",
}

# Rate limits ("count/period", period = second|minute|hour|day). Read at request
# time by apps.accounts.throttles. Per-IP limits are generous because many
# people may share one network (e.g. an expo venue); per-phone limits are strict.
API_THROTTLE_RATES = {
    "auth_login_ip": "60/hour",
    "auth_login_phone": "10/hour",
    "auth_signup_ip": "30/hour",
    "phone_code_ip": "60/hour",
}

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
# Never log passwords, OTPs, arrival codes, raw voice, message bodies, CNIC
# data, or provider credentials (SEC-04). Every line carries the request ID.
LOG_LEVEL = env_str("DJANGO_LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.log_filters.RequestIDLogFilter"},
    },
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

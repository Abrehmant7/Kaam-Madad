"""Settings shared by every environment (development, production, test).

Environment-specific modules import ``*`` from here and override what differs.
Configuration comes from environment variables; see ``.env.example`` in the
repository root for every supported variable.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from apps.core.static_cache import is_immutable_asset
from config.env import env_int, env_list, env_str

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
]

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

# Sessions live in PostgreSQL; cookies are HttpOnly. SameSite=Lax blocks
# cross-site POSTs carrying the session while allowing normal navigation.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

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
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Deny by default; public endpoints (e.g. health) opt in explicitly.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "apps.core.api.exception_handler.api_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
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

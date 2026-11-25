"""Production settings: HTTPS, secure cookies, and fail-fast configuration checks.

Frontend and API are served from one origin by this Django deployment
(WhiteNoise serves the Vite build; Django serves index.html for client routes).
"""

from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_int

from .base import *  # noqa: F403

DEBUG = False

# Fail fast instead of starting with an unsafe configuration.
if not SECRET_KEY or len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure"):  # noqa: F405
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a random value of at least 50 characters in production."
    )
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must list the production host name(s).")

# --- HTTPS and cookies (SEC-01) ---
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
# Platform health probes often call over plain HTTP inside the private network.
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/"]
if env_bool("DJANGO_SECURE_PROXY_SSL_HEADER", False):
    # Only enable behind a proxy that always sets/overwrites X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 3600, minimum=0)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Hashed, compressed static files for the admin; WhiteNoise serves them.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Reuse connections for a minute by default in production.
DATABASES["default"]["CONN_MAX_AGE"] = env_int("DJANGO_CONN_MAX_AGE", 60, minimum=0)  # noqa: F405

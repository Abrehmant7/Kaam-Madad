"""Local development settings. Never use these for a deployed environment."""

import warnings

from .base import *  # noqa: F403

DEBUG = True

# STATIC_ROOT is only populated by `collectstatic` for production. In development
# WhiteNoise serves static files from app directories via Django's finders.
WHITENOISE_USE_FINDERS = True
warnings.filterwarnings("ignore", message=r"No directory at: .*staticfiles", category=UserWarning)

# A fixed, clearly insecure key is acceptable only for local development.
if not SECRET_KEY:  # noqa: F405
    SECRET_KEY = "django-insecure-local-development-only-do-not-deploy"

if not ALLOWED_HOSTS:  # noqa: F405
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

if not CSRF_TRUSTED_ORIGINS:  # noqa: F405
    CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

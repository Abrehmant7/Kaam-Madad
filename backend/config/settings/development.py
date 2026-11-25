"""Local development settings. Never use these for a deployed environment."""

import warnings

from config.env import check_simulation_allowed

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

# Local development is a demo deployment with the simulated phone-code provider
# unless the environment says otherwise.
DEPLOYMENT_MODE = DEPLOYMENT_MODE or DEPLOYMENT_MODE_DEMO  # noqa: F405
PHONE_VERIFICATION_PROVIDER = PHONE_VERIFICATION_PROVIDER or PHONE_PROVIDER_DEMO  # noqa: F405
check_simulation_allowed(DEPLOYMENT_MODE, PHONE_VERIFICATION_PROVIDER)

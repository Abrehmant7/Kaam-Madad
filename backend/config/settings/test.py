"""Settings for the automated test suite (runs against a real PostgreSQL test database).

Usage: python manage.py test --settings=config.settings.test
"""

from .development import *  # noqa: F403

# Fast hashing keeps tests quick. Never use this hasher outside tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Keep test output readable; warnings and errors still surface.
LOGGING["loggers"]["apps"]["level"] = "ERROR"  # noqa: F405
LOGGING["loggers"]["django"]["level"] = "ERROR"  # noqa: F405

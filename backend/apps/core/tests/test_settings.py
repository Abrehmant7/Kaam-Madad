"""Production settings guards, checked in fresh interpreters so env changes are isolated."""

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[3]
VALID_SECRET = "x" * 30 + "-production-like-test-secret-key-0123456789"

PRINT_SECURITY = (
    "import django; django.setup(); from django.conf import settings as s; "
    "print(s.DEBUG, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SESSION_COOKIE_HTTPONLY, "
    "s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS > 0)"
)


def run_with_production_settings(code: str, **env_overrides: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.production", **env_overrides}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


class ProductionSettingsTests(SimpleTestCase):
    def test_refuses_to_start_without_secret_key(self):
        result = run_with_production_settings(PRINT_SECURITY, DJANGO_SECRET_KEY="", DJANGO_ALLOWED_HOSTS="example.org")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_refuses_insecure_development_key(self):
        result = run_with_production_settings(
            PRINT_SECURITY,
            DJANGO_SECRET_KEY="django-insecure-" + "x" * 60,
            DJANGO_ALLOWED_HOSTS="example.org",
        )
        self.assertNotEqual(result.returncode, 0)

    def test_refuses_to_start_without_allowed_hosts(self):
        result = run_with_production_settings(PRINT_SECURITY, DJANGO_SECRET_KEY=VALID_SECRET, DJANGO_ALLOWED_HOSTS="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_ALLOWED_HOSTS", result.stderr)

    def test_secure_defaults(self):
        result = run_with_production_settings(
            PRINT_SECURITY, DJANGO_SECRET_KEY=VALID_SECRET, DJANGO_ALLOWED_HOSTS="example.org"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["False", "True", "True", "True", "True", "True"])

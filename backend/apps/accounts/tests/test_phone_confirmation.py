import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import PhoneVerificationChallenge as Challenge

User = get_user_model()
PASSWORD = "Strong-Pass-2026!"
BACKEND_DIR = Path(__file__).resolve().parents[3]


class DemoPhoneConfirmationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("03001234567", PASSWORD, role=User.Role.WORKER)
        self.client.force_login(self.user)

    def start(self):
        return self.client.post(reverse("auth-phone-confirmation"))

    def verify(self, code):
        return self.client.post(reverse("auth-phone-confirmation-verify"), {"code": code}, format="json")

    def age_latest_challenge(self, seconds):
        challenge = Challenge.objects.filter(user=self.user).latest("created_at")
        Challenge.objects.filter(pk=challenge.pk).update(
            created_at=challenge.created_at - timedelta(seconds=seconds),
            expires_at=challenge.expires_at - timedelta(seconds=seconds),
        )

    def test_status_before_start(self):
        body = self.client.get(reverse("auth-phone-confirmation")).json()
        self.assertEqual(body["status"], "unconfirmed")
        self.assertIsNone(body["active_code"])
        self.assertEqual(body["provider"], {"provider": "demo", "available": True, "simulated": True})

    def test_demo_flow_confirms_with_demo_method(self):
        with self.assertNoLogs("apps", level="DEBUG"):
            response = self.start()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        code = body["demo"]["code"]
        self.assertRegex(code, r"^\d{6}$")
        self.assertIn("DEMO ONLY", body["demo"]["notice"])
        self.assertEqual(body["active_code"]["attempts_remaining"], 5)
        self.assertEqual(body["active_code"]["expires_in_seconds"], 600)

        stored = Challenge.objects.get(user=self.user)
        self.assertNotIn(code, stored.code_digest)
        self.assertEqual(len(stored.code_digest), 64)
        # The code is never retrievable afterwards.
        self.assertNotIn("demo", self.client.get(reverse("auth-phone-confirmation")).json())

        confirmed = self.verify(code)
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["user"]["phone_confirmation"]["status"], "confirmed")
        self.assertEqual(confirmed.json()["user"]["phone_confirmation"]["method"], "demo")
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_confirmation_method, "demo")
        self.assertIsNotNone(self.user.phone_confirmed_at)

        # Consumed codes cannot be reused; a confirmed phone cannot request more codes.
        self.assertEqual(self.verify(code).json()["error"]["code"], "no_active_code")
        again = self.start()
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["error"]["code"], "phone_already_confirmed")

    def test_accepts_urdu_digits(self):
        code = self.start().json()["demo"]["code"]
        urdu = code.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        self.assertEqual(self.verify(urdu).status_code, 200)

    def test_rejects_malformed_code(self):
        self.start()
        response = self.verify("12ab56")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["fields"]["code"][0]["code"], "invalid_code_format")

    def test_wrong_codes_are_bounded(self):
        code = self.start().json()["demo"]["code"]
        wrong = "000000" if code != "000000" else "111111"
        for remaining in (4, 3, 2, 1):
            response = self.verify(wrong)
            self.assertEqual(response.json()["error"]["code"], "code_incorrect")
            self.assertEqual(response.json()["error"]["details"]["attempts_remaining"], remaining)
        final = self.verify(wrong)
        self.assertEqual(final.status_code, 429)
        self.assertEqual(final.json()["error"]["code"], "too_many_attempts")
        challenge = Challenge.objects.get(user=self.user)
        self.assertEqual(challenge.invalidation_reason, "too_many_attempts")
        # Even the right code no longer works.
        self.assertEqual(self.verify(code).json()["error"]["code"], "no_active_code")
        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_confirmed_at)

    def test_expired_code(self):
        code = self.start().json()["demo"]["code"]
        self.age_latest_challenge(601)
        response = self.verify(code)
        self.assertEqual(response.json()["error"]["code"], "code_expired")
        self.assertEqual(Challenge.objects.get(user=self.user).invalidation_reason, "expired")

    def test_resend_cooldown_and_supersede(self):
        first = self.start().json()["demo"]["code"]
        too_soon = self.start()
        self.assertEqual(too_soon.status_code, 429)
        self.assertEqual(too_soon.json()["error"]["code"], "resend_too_soon")
        self.assertGreater(too_soon.json()["error"]["details"]["retry_after_seconds"], 0)

        self.age_latest_challenge(61)
        second = self.start().json()["demo"]["code"]
        old = Challenge.objects.filter(user=self.user).order_by("created_at").first()
        self.assertEqual(old.invalidation_reason, "superseded")
        self.assertEqual(Challenge.objects.filter(user=self.user, consumed_at=None, invalidated_at=None).count(), 1)
        if first != second:
            self.assertEqual(self.verify(first).json()["error"]["code"], "code_incorrect")
        self.assertEqual(self.verify(second).status_code, 200)

    def test_hourly_send_limit(self):
        for _ in range(5):
            self.start()
            self.age_latest_challenge(61)
        response = self.start()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["code"], "send_limit_reached")
        self.assertEqual(Challenge.objects.filter(user=self.user).count(), 5)

    def test_code_bound_to_phone_number(self):
        code = self.start().json()["demo"]["code"]
        User.objects.filter(pk=self.user.pk).update(phone_number="+923009999999")
        self.assertEqual(self.verify(code).json()["error"]["code"], "no_active_code")

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.start().status_code, 401)
        self.assertEqual(self.verify("123456").status_code, 401)


@override_settings(DEPLOYMENT_MODE="live", PHONE_VERIFICATION_PROVIDER="unconfigured")
class UnconfiguredProviderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("03001234567", PASSWORD, role=User.Role.CUSTOMER)
        self.client.force_login(self.user)

    def test_honest_unavailable_response(self):
        status_body = self.client.get(reverse("auth-phone-confirmation")).json()
        self.assertFalse(status_body["provider"]["available"])
        response = self.client.post(reverse("auth-phone-confirmation"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "phone_verification_unavailable")
        self.assertNotIn("demo", response.json())
        self.assertFalse(Challenge.objects.exists())

    @override_settings(PHONE_VERIFICATION_PROVIDER="demo")
    def test_demo_provider_is_refused_outside_demo_mode(self):
        # Settings validation blocks this at startup; the service refuses it again at runtime.
        response = self.client.post(reverse("auth-phone-confirmation"))
        self.assertEqual(response.status_code, 503)
        self.assertFalse(Challenge.objects.exists())


class ProductionSimulationGuardTests(SimpleTestCase):
    """Production settings must refuse simulated authentication in a live deployment."""

    def run_production(self, **env):
        base_env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "DJANGO_SECRET_KEY": "x" * 30 + "-production-like-test-secret-key-0123456789",
            "DJANGO_ALLOWED_HOSTS": "example.org",
            "APP_DEPLOYMENT_MODE": "",
            "PHONE_VERIFICATION_PROVIDER": "",
        }
        code = "import django; django.setup(); from django.conf import settings as s; print(s.DEPLOYMENT_MODE, s.PHONE_VERIFICATION_PROVIDER)"
        return subprocess.run(
            [sys.executable, "-c", code], cwd=BACKEND_DIR, env={**base_env, **env},
            capture_output=True, text=True, timeout=60,
        )

    def test_defaults_to_live_without_simulation(self):
        result = self.run_production()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["live", "unconfigured"])

    def test_live_mode_rejects_demo_provider(self):
        result = self.run_production(PHONE_VERIFICATION_PROVIDER="demo")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only allowed when APP_DEPLOYMENT_MODE=demo", result.stderr)

    def test_explicit_demo_deployment_may_use_demo_provider(self):
        result = self.run_production(APP_DEPLOYMENT_MODE="demo", PHONE_VERIFICATION_PROVIDER="demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["demo", "demo"])

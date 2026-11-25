from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()

PASSWORD = "Strong-Pass-2026!"
SIGNUP = {
    "phone_number": "0300-1234567",
    "password": PASSWORD,
    "password_confirm": PASSWORD,
    "role": "worker",
    "preferred_language": "ur",
}


def field_codes(response, field):
    return [item["code"] for item in response.json()["error"]["fields"].get(field, [])]


class SignupTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_signup_creates_account_logs_in_and_masks_phone(self):
        response = self.client.post(reverse("auth-signup"), SIGNUP, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body["authenticated"])
        user_json = body["user"]
        self.assertEqual(user_json["role"], "worker")
        self.assertEqual(user_json["preferred_language"], "ur")
        self.assertEqual(user_json["phone_number_masked"], "+92 3** ***4567")
        self.assertNotIn("3001234567", response.content.decode())
        self.assertEqual(user_json["phone_confirmation"], {"status": "unconfirmed", "method": None, "confirmed_at": None})
        self.assertTrue(user_json["is_demo"])  # development settings run in demo mode

        user = User.objects.get(phone_number="+923001234567")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotIn(PASSWORD, user.password)
        self.assertFalse(user.is_staff or user.is_superuser)

        me = self.client.get(reverse("auth-me")).json()
        self.assertTrue(me["authenticated"])
        self.assertEqual(me["user"]["id"], str(user.id))

    @override_settings(DEPLOYMENT_MODE="live", PHONE_VERIFICATION_PROVIDER="unconfigured")
    def test_live_mode_accounts_are_not_demo(self):
        response = self.client.post(reverse("auth-signup"), {**SIGNUP, "role": "customer"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["user"]["is_demo"])

    def test_phone_uniqueness_across_formats(self):
        User.objects.create_user("03001234567", PASSWORD)
        response = self.client.post(reverse("auth-signup"), {**SIGNUP, "phone_number": "+92 300 1234567"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(field_codes(response, "phone_number"), ["phone_taken"])

    def test_invalid_phone(self):
        response = self.client.post(reverse("auth-signup"), {**SIGNUP, "phone_number": "051-2345678"}, format="json")
        self.assertEqual(field_codes(response, "phone_number"), ["invalid_pk_mobile"])

    def test_password_rules(self):
        cases = {
            "short": ("Ab1!", "password_too_short"),
            "common": ("password123", "password_too_common"),
            "numeric": ("83920174652", "password_entirely_numeric"),
        }
        for name, (password, code) in cases.items():
            with self.subTest(name):
                response = self.client.post(
                    reverse("auth-signup"),
                    {**SIGNUP, "password": password, "password_confirm": password},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(code, field_codes(response, "password"))
        self.assertFalse(User.objects.exists())

    def test_password_confirmation_must_match(self):
        response = self.client.post(reverse("auth-signup"), {**SIGNUP, "password_confirm": "Different-2026!"}, format="json")
        self.assertEqual(field_codes(response, "password_confirm"), ["password_mismatch"])

    def test_cannot_escalate_privileges_or_set_internal_fields(self):
        for extra in (
            {"is_staff": True},
            {"is_superuser": True},
            {"is_active": False},
            {"is_demo": False},
            {"phone_confirmed_at": "2026-01-01T00:00:00Z"},
            {"phone_confirmation_method": "sms"},
            {"groups": [1]},
        ):
            with self.subTest(extra=extra):
                response = self.client.post(reverse("auth-signup"), {**SIGNUP, **extra}, format="json")
                self.assertEqual(response.status_code, 400)
                field = next(iter(extra))
                self.assertEqual(field_codes(response, field), ["unexpected_field"])
        self.assertFalse(User.objects.exists())

    def test_role_must_be_marketplace_role(self):
        for role in ("staff", "admin", ""):
            with self.subTest(role=role):
                response = self.client.post(reverse("auth-signup"), {**SIGNUP, "role": role}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("role", response.json()["error"]["fields"])

    def test_signup_while_logged_in_is_rejected(self):
        self.client.post(reverse("auth-signup"), SIGNUP, format="json")
        response = self.client.post(reverse("auth-signup"), {**SIGNUP, "phone_number": "03111111111"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "already_authenticated")


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("03001234567", PASSWORD, role=User.Role.CUSTOMER)

    def login(self, phone="0300 1234567", password=PASSWORD):
        return self.client.post(reverse("auth-login"), {"phone_number": phone, "password": password}, format="json")

    def test_login_with_any_phone_format_and_session_persists(self):
        response = self.login("+92 300 1234567")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["role"], "customer")
        self.assertIn("sessionid", response.cookies)
        self.assertTrue(response.cookies["sessionid"]["httponly"])
        # A later request in the same "browser" is still authenticated.
        self.assertTrue(self.client.get(reverse("auth-me")).json()["authenticated"])

    def test_login_rotates_session_key(self):
        # Session fixation: a session that existed before login must not survive it.
        from django.contrib.sessions.backends.db import SessionStore

        planted = SessionStore()
        planted["probe"] = 1
        planted.save()
        self.client.cookies["sessionid"] = planted.session_key
        after = self.login().cookies["sessionid"].value
        self.assertNotEqual(after, planted.session_key)

    def test_wrong_password_and_unknown_phone_give_same_error(self):
        for response in (self.login(password="Wrong-Pass-2026!"), self.login(phone="03119999999")):
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "invalid_credentials")
        self.assertFalse(self.client.get(reverse("auth-me")).json()["authenticated"])

    def test_inactive_account(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.login().json()["error"]["code"], "account_inactive")
        # Without the right password, suspension is not revealed.
        self.assertEqual(self.login(password="Wrong-Pass-2026!").json()["error"]["code"], "invalid_credentials")

    def test_deactivated_user_loses_access_mid_session(self):
        self.login()
        self.assertEqual(self.client.get(reverse("auth-phone-confirmation")).status_code, 200)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertFalse(self.client.get(reverse("auth-me")).json()["authenticated"])
        response = self.client.get(reverse("auth-phone-confirmation"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "not_authenticated")

    def test_logout(self):
        self.login()
        self.assertEqual(self.client.post(reverse("auth-logout")).status_code, 204)
        self.assertFalse(self.client.get(reverse("auth-me")).json()["authenticated"])
        self.assertEqual(self.client.get(reverse("auth-phone-confirmation")).status_code, 401)
        # Idempotent.
        self.assertEqual(self.client.post(reverse("auth-logout")).status_code, 204)

    def test_malformed_phone_is_a_field_error(self):
        response = self.login(phone="hello")
        self.assertEqual(field_codes(response, "phone_number"), ["invalid_pk_mobile"])

    @override_settings(API_THROTTLE_RATES={"auth_login_phone": "3/hour", "auth_login_ip": "100/hour"})
    def test_login_attempts_are_rate_limited_per_phone(self):
        for _ in range(3):
            self.assertEqual(self.login(password="Wrong-Pass-2026!").status_code, 400)
        response = self.login()  # even the correct password is refused now
        self.assertEqual(response.status_code, 429)
        error = response.json()["error"]
        self.assertEqual(error["code"], "throttled")
        self.assertGreater(error["details"]["retry_after_seconds"], 0)
        self.assertIn("Retry-After", response)
        # Another phone number from the same network is unaffected.
        User.objects.create_user("03111234567", PASSWORD)
        self.assertEqual(self.login(phone="03111234567").status_code, 200)

    @override_settings(API_THROTTLE_RATES={"auth_signup_ip": "2/hour"})
    def test_signup_is_rate_limited_per_ip(self):
        client = APIClient()
        for phone in ("03211111111", "03211111112"):
            client.post(reverse("auth-signup"), {**SIGNUP, "phone_number": phone}, format="json")
            client.post(reverse("auth-logout"))
        response = client.post(reverse("auth-signup"), {**SIGNUP, "phone_number": "03211111113"}, format="json")
        self.assertEqual(response.status_code, 429)


class CsrfTests(TestCase):
    """Real CSRF enforcement (the default test client skips CSRF checks)."""

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        User.objects.create_user("03001234567", PASSWORD, role=User.Role.WORKER)

    def csrf_token(self):
        response = self.client.get(reverse("auth-csrf"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        self.assertFalse(response.cookies["csrftoken"]["httponly"])  # the SPA must read it
        return response.json()["csrf_token"]

    def test_login_without_token_is_rejected(self):
        response = self.client.post(reverse("auth-login"), {"phone_number": "03001234567", "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "csrf_failed")
        self.assertFalse(self.client.get(reverse("auth-me")).json()["authenticated"])

    def test_signup_without_token_is_rejected(self):
        response = self.client.post(reverse("auth-signup"), {**SIGNUP, "phone_number": "03111111111"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "csrf_failed")
        self.assertFalse(User.objects.filter(phone_number="+923111111111").exists())

    def test_login_and_mutations_with_token(self):
        token = self.csrf_token()
        response = self.client.post(
            reverse("auth-login"),
            {"phone_number": "03001234567", "password": PASSWORD},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        # Django rotates the token at login; the old one no longer works.
        new_token = self.client.cookies["csrftoken"].value
        stale = self.client.patch(reverse("auth-language"), {"preferred_language": "en"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(stale.status_code, 403)
        ok = self.client.patch(reverse("auth-language"), {"preferred_language": "en"}, format="json", HTTP_X_CSRFTOKEN=new_token)
        self.assertEqual(ok.status_code, 200)
        missing = self.client.post(reverse("auth-logout"))
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(self.client.post(reverse("auth-logout"), HTTP_X_CSRFTOKEN=new_token).status_code, 204)


class LanguagePreferenceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user("03001234567", PASSWORD, role=User.Role.WORKER)

    def test_requires_login(self):
        response = self.client.patch(reverse("auth-language"), {"preferred_language": "en"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_updates_and_persists_preference(self):
        self.client.force_login(self.user)
        response = self.client.patch(reverse("auth-language"), {"preferred_language": "en"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["preferred_language"], "en")
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_language, "en")
        # A new session (e.g. another device) sees the stored preference.
        other = APIClient()
        other.post(reverse("auth-login"), {"phone_number": "03001234567", "password": PASSWORD}, format="json")
        self.assertEqual(other.get(reverse("auth-me")).json()["user"]["preferred_language"], "en")

    def test_cannot_change_role_or_other_fields(self):
        self.client.force_login(self.user)
        for payload in ({"role": "customer"}, {"preferred_language": "en", "role": "customer"}, {"is_staff": True}):
            with self.subTest(payload=payload):
                response = self.client.patch(reverse("auth-language"), payload, format="json")
                self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, "worker")
        self.assertFalse(self.user.is_staff)

    def test_rejects_unknown_language(self):
        self.client.force_login(self.user)
        response = self.client.patch(reverse("auth-language"), {"preferred_language": "fr"}, format="json")
        self.assertEqual(field_codes(response, "preferred_language"), ["invalid_choice"])


@override_settings(ROOT_URLCONF="apps.accounts.tests.urls_roles")
class RolePermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.worker = User.objects.create_user("03001111111", PASSWORD, role=User.Role.WORKER)
        self.customer = User.objects.create_user("03002222222", PASSWORD, role=User.Role.CUSTOMER)
        self.staff = User.objects.create_superuser("03003333333", PASSWORD)

    def status(self, user, path):
        self.client.logout()
        if user:
            self.client.force_login(user)
        return self.client.get(path)

    def test_role_enforcement(self):
        self.assertEqual(self.status(self.worker, "/api/v1/test/worker/").status_code, 200)
        self.assertEqual(self.status(self.customer, "/api/v1/test/customer/").status_code, 200)

        denied = self.status(self.customer, "/api/v1/test/worker/")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["code"], "worker_role_required")
        self.assertEqual(self.status(self.worker, "/api/v1/test/customer/").status_code, 403)

        # Staff authority does not imply a marketplace role.
        self.assertEqual(self.status(self.staff, "/api/v1/test/marketplace/").status_code, 403)
        self.assertEqual(self.status(None, "/api/v1/test/worker/").status_code, 401)


class ClientConfigTests(TestCase):
    def test_config_reports_demo_mode(self):
        body = APIClient().get(reverse("client-config")).json()
        self.assertEqual(body["deployment_mode"], "demo")
        self.assertEqual(body["phone_verification"], {"provider": "demo", "available": True, "simulated": True})
        self.assertEqual(body["default_language"], "ur")

    @override_settings(DEPLOYMENT_MODE="live", PHONE_VERIFICATION_PROVIDER="unconfigured")
    def test_config_reports_unavailable_phone_verification(self):
        body = APIClient().get(reverse("client-config")).json()
        self.assertEqual(body["deployment_mode"], "live")
        self.assertEqual(body["phone_verification"], {"provider": "unconfigured", "available": False, "simulated": False})

import uuid

from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

User = get_user_model()

PASSWORD = "a-Long-test-passphrase-91"


class UserModelTests(TestCase):
    def test_custom_user_model_is_active(self):
        self.assertEqual(User._meta.label, "accounts.User")
        self.assertEqual(User.USERNAME_FIELD, "phone_number")

    def test_create_user_normalises_phone_and_hashes_password(self):
        user = User.objects.create_user("0300-1234567", PASSWORD, role=User.Role.WORKER)
        user.refresh_from_db()
        self.assertIsInstance(user.pk, uuid.UUID)
        self.assertEqual(user.phone_number, "+923001234567")
        self.assertNotEqual(user.password, PASSWORD)
        self.assertNotIn(PASSWORD, user.password)
        self.assertTrue(user.check_password(PASSWORD))

    def test_defaults(self):
        user = User.objects.create_user("03001234567", PASSWORD)
        self.assertEqual(user.preferred_language, User.Language.URDU)
        self.assertEqual(user.role, "")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_demo)
        self.assertFalse(user.is_worker)
        self.assertFalse(user.is_customer)

    def test_create_user_without_password_has_unusable_password(self):
        user = User.objects.create_user("03001234567")
        self.assertFalse(user.has_usable_password())

    def test_create_user_rejects_invalid_phone(self):
        with self.assertRaises(ValidationError):
            User.objects.create_user("0512345678", PASSWORD)

    def test_phone_is_unique_across_input_formats(self):
        User.objects.create_user("03001234567", PASSWORD)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("+92 300 1234567", PASSWORD)

    def test_create_superuser_sets_server_side_staff_flags(self):
        admin = User.objects.create_superuser("03111234567", PASSWORD)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.role, "")

    def test_create_superuser_rejects_non_staff_flags(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser("03111234567", PASSWORD, is_staff=False)
        with self.assertRaises(ValueError):
            User.objects.create_superuser("03111234567", PASSWORD, is_superuser=False)

    def test_marketplace_role_grants_no_staff_permission(self):
        worker = User.objects.create_user("03001234567", PASSWORD, role=User.Role.WORKER)
        customer = User.objects.create_user("03211234567", PASSWORD, role=User.Role.CUSTOMER)
        for user in (worker, customer):
            self.assertFalse(user.is_staff)
            self.assertFalse(user.has_perm("accounts.change_user"))
        self.assertTrue(worker.is_worker)
        self.assertTrue(customer.is_customer)

    def test_natural_key_lookup_accepts_any_format(self):
        user = User.objects.create_user("03001234567", PASSWORD)
        self.assertEqual(User.objects.get_by_natural_key("0300 1234567"), user)
        self.assertEqual(User.objects.get_by_natural_key("۰۳۰۰۱۲۳۴۵۶۷"), user)
        with self.assertRaises(User.DoesNotExist):
            User.objects.get_by_natural_key("not-a-number")

    def test_authenticate_with_formatted_phone(self):
        User.objects.create_user("03001234567", PASSWORD)
        self.assertIsNotNone(authenticate(phone_number="+92 300 1234567", password=PASSWORD))
        self.assertIsNone(authenticate(phone_number="03001234567", password="wrong-password"))

    def test_inactive_user_cannot_authenticate(self):
        User.objects.create_user("03001234567", PASSWORD, is_active=False)
        self.assertIsNone(authenticate(phone_number="03001234567", password=PASSWORD))

    def test_str_is_masked(self):
        user = User.objects.create_user("03001234567", PASSWORD)
        self.assertEqual(str(user), "+92 3** ***4567")
        self.assertNotIn("3001234567", str(user))

    def test_save_normalises_phone(self):
        user = User(phone_number="0300 7654321")
        user.set_unusable_password()
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.phone_number, "+923007654321")

    def test_full_clean_normalises_and_validates(self):
        user = User(phone_number="0300-7654321")
        user.set_unusable_password()
        user.full_clean()
        self.assertEqual(user.phone_number, "+923007654321")

        invalid = User(phone_number="0512345678")
        invalid.set_unusable_password()
        with self.assertRaises(ValidationError) as ctx:
            invalid.full_clean()
        self.assertIn("phone_number", ctx.exception.message_dict)


class UserDatabaseConstraintTests(TestCase):
    """Invariants hold in PostgreSQL even when Python-level validation is bypassed."""

    def setUp(self):
        self.user = User.objects.create_user("03001234567", PASSWORD)

    def assert_rejected(self, **values):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=self.user.pk).update(**values)

    def test_rejects_unnormalised_phone(self):
        self.assert_rejected(phone_number="03001234567")

    def test_rejects_landline_in_e164(self):
        self.assert_rejected(phone_number="+92512345678")

    def test_rejects_unknown_role(self):
        self.assert_rejected(role="staff")

    def test_rejects_unknown_language(self):
        self.assert_rejected(preferred_language="fr")

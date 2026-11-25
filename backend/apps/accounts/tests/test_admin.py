from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

PASSWORD = "a-Long-test-passphrase-91"


class UserAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser("03111234567", PASSWORD)
        self.worker = User.objects.create_user("03001234567", PASSWORD, role=User.Role.WORKER)
        self.client.force_login(self.admin_user)

    def test_changelist_shows_masked_phone_numbers(self):
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+92 3** ***4567")
        self.assertNotContains(response, "+923001234567")

    def test_change_page_loads(self):
        response = self.client.get(reverse("admin:accounts_user_change", args=[self.worker.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+923001234567")

    def test_add_user_normalises_phone(self):
        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "phone_number": "0321 765-4321",
                "role": User.Role.CUSTOMER,
                "preferred_language": User.Language.ENGLISH,
                "usable_password": "true",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 302)
        created = User.objects.get(phone_number="+923217654321")
        self.assertEqual(created.role, User.Role.CUSTOMER)
        self.assertFalse(created.is_staff)
        self.assertTrue(created.check_password(PASSWORD))

    def test_add_user_rejects_duplicate_in_other_format(self):
        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "phone_number": "+92 300 1234567",
                "role": User.Role.CUSTOMER,
                "preferred_language": User.Language.URDU,
                "usable_password": "false",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with this phone number already exists.")
        self.assertEqual(User.objects.filter(phone_number="+923001234567").count(), 1)

    def test_search_accepts_formatted_phone(self):
        response = self.client.get(reverse("admin:accounts_user_changelist"), {"q": "0300-1234567"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["cl"].result_list), [self.worker])


class AdminAccessTests(TestCase):
    def test_marketplace_users_cannot_use_admin(self):
        for phone, role in (("03001111111", User.Role.WORKER), ("03002222222", User.Role.CUSTOMER)):
            user = User.objects.create_user(phone, PASSWORD, role=role)
            self.client.force_login(user)
            response = self.client.get(reverse("admin:index"))
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("admin:login"), response["Location"])

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertEqual(response.status_code, 302)

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()
PASSWORD = "Strong-Pass-2026!"
CARDS = Path(__file__).resolve().parents[4] / "docs" / "demo" / "cnic"

GOOD_WORK = {
    "trade": "electrician",
    "services_offered": ["elec_fan_install", "elec_wiring_repair"],
    "primary_specialities": ["elec_fan_install"],
    "services_not_offered": ["elec_ups_inverter"],
}
GOOD_AREAS = {"city": "islamabad", "service_areas": ["isb-g-9", "isb-g-10"]}


class WorkerApiTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp(prefix="kaam-madad-m4-")
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        with open(Path(tempfile.gettempdir()) / "seed-m4.log", "w") as log:
            call_command("seed_catalog", stdout=log)
            call_command("seed_demo_registry", stdout=log)

    def setUp(self):
        self.worker = User.objects.create_user("03001111111", PASSWORD, role=User.Role.WORKER, is_demo=True)
        self.client = APIClient()
        self.client.force_login(self.worker)

    def other_client(self, phone="03002222222", role=User.Role.WORKER, **extra):
        user = User.objects.create_user(phone, PASSWORD, role=role, **extra)
        client = APIClient()
        client.force_login(user)
        return user, client

    def me(self, client=None):
        return (client or self.client).get(reverse("worker-me"))

    def put_work(self, payload=None, client=None):
        return (client or self.client).put(reverse("worker-work"), payload or GOOD_WORK, format="json")

    def put_areas(self, payload=None, client=None):
        return (client or self.client).put(reverse("worker-areas"), payload or GOOD_AREAS, format="json")

    def complete_profile(self, client=None):
        self.assertEqual(self.put_work(client=client).status_code, 200)
        self.assertEqual(self.put_areas(client=client).status_code, 200)

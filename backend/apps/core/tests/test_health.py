import copy
import socket
import uuid
from unittest import mock

from django.db import OperationalError, connections
from django.test import TestCase
from django.urls import reverse

from apps.core import health

SECRET_LOOKING_TEXT = "password=hunter2 host=db.internal user=roshan"


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _unreachable_database_connection():
    """A real PostgreSQL connection wrapper pointed at a closed local port."""
    default = connections["default"]
    settings_dict = copy.deepcopy(default.settings_dict)
    settings_dict.update(HOST="127.0.0.1", PORT=str(_unused_local_port()))
    settings_dict["OPTIONS"] = {**settings_dict.get("OPTIONS", {}), "connect_timeout": 2}
    return default.__class__(settings_dict, alias="unreachable-for-readiness-test")


class LivenessTests(TestCase):
    def test_live_returns_ok_without_touching_the_database(self):
        with self.assertNumQueries(0):
            response = self.client.get(reverse("health-live"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_live_is_public_and_not_cached(self):
        response = self.client.get("/api/v1/health/live/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])

    def test_response_carries_request_id(self):
        response = self.client.get(reverse("health-live"))
        uuid.UUID(response["X-Request-ID"])  # raises if not a UUID

    def test_client_supplied_request_id_is_ignored(self):
        response = self.client.get(reverse("health-live"), headers={"X-Request-ID": "attacker\nforged"})
        self.assertNotEqual(response["X-Request-ID"], "attacker\nforged")
        uuid.UUID(response["X-Request-ID"])

    def test_live_rejects_unsupported_methods_with_error_envelope(self):
        response = self.client.post(reverse("health-live"))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"]["code"], "method_not_allowed")


class ReadinessTests(TestCase):
    def test_ready_when_database_is_reachable(self):
        response = self.client.get(reverse("health-ready"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "checks": {"database": "ok"}})
        self.assertIn("no-store", response["Cache-Control"])

    def test_check_database_against_real_unreachable_server(self):
        unreachable = _unreachable_database_connection()
        try:
            self.assertFalse(health.check_database(unreachable))
        finally:
            unreachable.close()

    def test_ready_returns_503_when_database_is_unreachable(self):
        unreachable = _unreachable_database_connection()
        try:
            with mock.patch.object(health, "get_database_connection", return_value=unreachable):
                with self.assertLogs("apps.core.health", level="WARNING") as logs:
                    response = self.client.get(reverse("health-ready"))
        finally:
            unreachable.close()

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["error"]["code"], "service_not_ready")
        self.assertEqual(body["error"]["details"], {"checks": {"database": "unavailable"}})
        self.assertEqual(body["error"]["request_id"], response["X-Request-ID"])
        self.assertIn("no-store", response["Cache-Control"])
        # The log names the failure class but not the driver's message.
        self.assertIn("OperationalError", logs.output[0])
        self.assertNotIn("127.0.0.1", logs.output[0])

    def test_ready_failure_never_exposes_internal_details(self):
        failing = mock.Mock()
        failing.cursor.side_effect = OperationalError(SECRET_LOOKING_TEXT)
        with mock.patch.object(health, "get_database_connection", return_value=failing):
            with self.assertLogs("apps.core.health", level="WARNING") as logs:
                response = self.client.get(reverse("health-ready"))

        self.assertEqual(response.status_code, 503)
        raw = response.content.decode()
        for fragment in ("hunter2", "db.internal", "password", "OperationalError", "Traceback"):
            self.assertNotIn(fragment, raw)
        self.assertNotIn("hunter2", "\n".join(logs.output))

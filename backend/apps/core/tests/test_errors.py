from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.exceptions import ErrorDetail

from apps.core.api.exception_handler import flatten_field_errors


class ApiNotFoundTests(TestCase):
    def test_unknown_api_path_returns_json_envelope(self):
        response = self.client.get("/api/v1/does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")
        error = response.json()["error"]
        self.assertEqual(error["code"], "not_found")
        self.assertTrue(error["message"])
        self.assertEqual(error["request_id"], response["X-Request-ID"])
        self.assertNotIn("fields", error)

    def test_unknown_api_path_is_not_served_by_spa(self):
        response = self.client.post("/api/anything")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")


@override_settings(ROOT_URLCONF="apps.core.tests.urls_errors")
class ErrorEnvelopeTests(TestCase):
    def test_validation_errors_have_flattened_field_codes(self):
        response = self.client.post(
            "/api/v1/test/validation/",
            {"phone_number": "0300123456789", "items": [{"amount": "12.50"}, {"amount": "abc"}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        error = response.json()["error"]
        self.assertEqual(error["code"], "validation_error")
        self.assertEqual(error["request_id"], response["X-Request-ID"])
        self.assertEqual(error["fields"]["phone_number"][0]["code"], "max_length")
        self.assertEqual(error["fields"]["items.1.amount"][0]["code"], "invalid")
        self.assertNotIn("items.0.amount", error["fields"])

    def test_non_field_validation_error(self):
        response = self.client.post(
            "/api/v1/test/validation/",
            {"phone_number": "0300", "items": []},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        fields = response.json()["error"]["fields"]
        self.assertEqual(fields["non_field_errors"], [{"code": "terms_conflict", "message": "Terms conflict."}])

    def test_malformed_json_is_parse_error(self):
        response = self.client.post("/api/v1/test/validation/", "{not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "parse_error")

    def test_application_error_with_details(self):
        response = self.client.post("/api/v1/test/conflict/")
        self.assertEqual(response.status_code, 409)
        error = response.json()["error"]
        self.assertEqual(error["code"], "quote_superseded")
        self.assertEqual(error["message"], "Quotation changed.")
        self.assertEqual(error["details"], {"current_version": 3})

    def test_default_permission_denies_anonymous(self):
        response = self.client.get("/api/v1/test/protected/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "not_authenticated")

    def test_unhandled_api_exception_returns_generic_json_500(self):
        self.client.raise_request_exception = False
        with self.assertLogs("django.request", level="ERROR"):
            response = self.client.get("/api/v1/test/crash/")
        self.assertEqual(response.status_code, 500)
        error = response.json()["error"]
        self.assertEqual(error["code"], "server_error")
        self.assertEqual(error["request_id"], response["X-Request-ID"])
        raw = response.content.decode()
        self.assertNotIn("hunter2", raw)
        self.assertNotIn("RuntimeError", raw)

    def test_unhandled_non_api_exception_uses_django_default(self):
        self.client.raise_request_exception = False
        with self.assertLogs("django.request", level="ERROR"):
            response = self.client.get("/crash-html/")
        self.assertEqual(response.status_code, 500)
        self.assertNotEqual(response.get("Content-Type"), "application/json")
        self.assertNotIn(b"secret internal detail", response.content)


class FlattenFieldErrorsTests(SimpleTestCase):
    def test_nested_structures(self):
        detail = {
            "name": [ErrorDetail("Required.", code="required")],
            "address": {"area": [ErrorDetail("Unknown area.", code="unknown_area")]},
            "items": [{}, {"qty": [ErrorDetail("Too many.", code="max_value")]}],
            "non_field_errors": [ErrorDetail("Conflict.", code="conflict")],
        }
        self.assertEqual(
            flatten_field_errors(detail),
            {
                "name": [{"code": "required", "message": "Required."}],
                "address.area": [{"code": "unknown_area", "message": "Unknown area."}],
                "items.1.qty": [{"code": "max_value", "message": "Too many."}],
                "non_field_errors": [{"code": "conflict", "message": "Conflict."}],
            },
        )

    def test_top_level_list(self):
        self.assertEqual(
            flatten_field_errors([ErrorDetail("Bad.", code="bad")]),
            {"non_field_errors": [{"code": "bad", "message": "Bad."}]},
        )

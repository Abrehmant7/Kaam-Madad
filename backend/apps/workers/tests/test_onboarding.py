from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import ServiceTag
from apps.workers.models import WorkerProfile

from .helpers import GOOD_AREAS, GOOD_WORK, User, WorkerApiTestCase


def field_codes(response, field):
    return [item["code"] for item in response.json()["error"]["fields"].get(field, [])]


class OnboardingFlowTests(WorkerApiTestCase):
    def test_new_worker_starts_at_work_step_and_resumes_after_each_step(self):
        body = self.me().json()
        self.assertEqual(body["onboarding"], {
            "complete": False, "next_step": "work",
            "steps": {"work": {"complete": False, "issues": ["required"]},
                      "areas": {"complete": False, "issues": ["required"]}},
        })
        self.assertEqual(self.put_work().status_code, 200)
        # A refresh or a new login reads the saved progress from the server.
        fresh = APIClient()
        fresh.force_login(self.worker)  # a new session for the same worker
        resumed = self.me(fresh).json()
        self.assertEqual(resumed["onboarding"]["next_step"], "areas")
        self.assertEqual(resumed["profile"]["primary_specialities"], ["elec_fan_install"])
        self.assertEqual(self.put_areas(client=fresh).status_code, 200)
        done = self.me(fresh).json()
        self.assertTrue(done["onboarding"]["complete"])
        self.assertIsNone(done["onboarding"]["next_step"])
        self.assertEqual(done["profile"]["service_areas"], ["isb-g-10", "isb-g-9"])
        self.assertTrue(done["profile"]["accepting_requests"])

    def test_profile_can_be_edited_after_completion(self):
        self.complete_profile()
        response = self.put_work({**GOOD_WORK, "services_offered": ["elec_fan_install"], "services_not_offered": []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["profile"]["services_offered"], ["elec_fan_install"])
        self.assertTrue(response.json()["onboarding"]["complete"])

    def test_cross_trade_services_are_rejected(self):
        response = self.put_work({**GOOD_WORK, "services_offered": ["elec_fan_install", "plmb_leak_repair"]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("unknown_service", field_codes(response, "services_offered"))
        self.assertFalse(WorkerProfile.objects.filter(user=self.worker, trade__isnull=False).exists())

    def test_main_speciality_must_be_an_offered_service(self):
        response = self.put_work({**GOOD_WORK, "primary_specialities": ["elec_light_fitting"]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("primary_not_offered", field_codes(response, "primary_specialities"))

    def test_offered_and_excluded_cannot_overlap(self):
        response = self.put_work({**GOOD_WORK, "services_not_offered": ["elec_wiring_repair"]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("offered_and_excluded_overlap", field_codes(response, "services_not_offered"))

    def test_selection_limits_and_required_fields(self):
        cases = [
            ({**GOOD_WORK, "primary_specialities": []}, "primary_specialities", "too_few"),
            ({**GOOD_WORK, "services_offered": [], "primary_specialities": []}, "services_offered", "too_few"),
            ({**GOOD_WORK, "services_offered": ["elec_fan_install", "elec_wiring_repair", "elec_new_wiring", "elec_fan_repair"],
              "primary_specialities": ["elec_fan_install", "elec_wiring_repair", "elec_new_wiring", "elec_fan_repair"]},
             "primary_specialities", "too_many"),
            ({**GOOD_WORK, "trade": ""}, "trade", "required"),
            ({**GOOD_WORK, "trade": "astronaut"}, "trade", "unknown_trade"),
        ]
        for payload, field, code in cases:
            with self.subTest(code=code):
                response = self.put_work(payload)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(code, field_codes(response, field))

    def test_unknown_fields_are_rejected(self):
        response = self.put_work({**GOOD_WORK, "accepting_requests": False})
        self.assertEqual(response.status_code, 400)

    def test_areas_outside_the_city_are_rejected(self):
        response = self.put_areas({"city": "islamabad", "service_areas": ["isb-g-9", "rwp-saddar"]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("area_not_in_city", field_codes(response, "service_areas"))
        cases = [
            ({"city": "islamabad", "service_areas": []}, "service_areas", "too_few"),
            ({"city": "islamabad", "service_areas": ["isb-nowhere"]}, "service_areas", "unknown_area"),
            ({"city": "karachi", "service_areas": ["isb-g-9"]}, "city", "unknown_city"),
            ({"city": "", "service_areas": ["isb-g-9"]}, "city", "required"),
        ]
        for payload, field, code in cases:
            with self.subTest(code=code):
                self.assertIn(code, field_codes(self.put_areas(payload), field))

    def test_completion_is_recomputed_when_the_catalog_changes(self):
        self.complete_profile()
        ServiceTag.objects.filter(code="elec_fan_install").update(is_active=False)
        body = self.me().json()
        self.assertFalse(body["onboarding"]["complete"])
        self.assertEqual(body["onboarding"]["next_step"], "work")

    def test_accepting_requests_is_separate_from_completion(self):
        response = self.client.patch(reverse("worker-preferences"), {"accepting_requests": False}, format="json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["profile"]["accepting_requests"])
        self.assertFalse(body["onboarding"]["complete"])  # unchanged by the preference

    def test_only_workers_can_use_the_worker_api(self):
        _, customer = self.other_client("03003333333", role=User.Role.CUSTOMER)
        self.assertEqual(self.me(customer).status_code, 403)
        self.assertEqual(self.put_work(client=customer).status_code, 403)
        anonymous = APIClient()
        self.assertIn(self.me(anonymous).status_code, (401, 403))

    def test_each_worker_only_sees_their_own_profile(self):
        self.complete_profile()
        _, other = self.other_client()
        body = self.me(other).json()
        self.assertIsNone(body["profile"]["trade"])
        self.assertEqual(body["onboarding"]["next_step"], "work")

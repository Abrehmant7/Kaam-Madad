from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Area, City, ServiceTag, SpecialityQuestion, Trade
from apps.catalog.speciality import validate_speciality_answers


def seed(*args) -> str:
    out = StringIO()
    call_command("seed_catalog", *args, stdout=out)
    return out.getvalue()


class SeedCommandTests(TestCase):
    def test_idempotent(self):
        first = seed()
        self.assertIn("Trades: 3 created", first)
        counts = [m.objects.count() for m in (Trade, ServiceTag, City, Area, SpecialityQuestion)]
        second = seed()
        self.assertIn("Trades: 0 created, 0 updated, 3 unchanged", second)
        self.assertIn("Service tags: 0 created, 0 updated", second)
        self.assertEqual(counts, [m.objects.count() for m in (Trade, ServiceTag, City, Area, SpecialityQuestion)])
        self.assertEqual(counts[:2], [3, 23])

    def test_updates_known_codes_keeps_staff_decisions_and_records(self):
        seed()
        Trade.objects.filter(code="plumber").update(label_en="Plumbing (edited)", is_active=False)
        staff_trade = Trade.objects.create(code="carpenter", label_en="Carpenter", label_ur="بڑھئی", icon="hammer")
        output = seed()
        self.assertIn("Trades: 0 created, 1 updated, 2 unchanged", output)
        plumber = Trade.objects.get(code="plumber")
        self.assertEqual(plumber.label_en, "Plumber")  # known record refreshed by code
        self.assertFalse(plumber.is_active)  # staff deactivation preserved
        self.assertTrue(Trade.objects.filter(pk=staff_trade.pk).exists())  # unrelated record untouched

    def test_dry_run_writes_nothing(self):
        output = seed("--dry-run")
        self.assertIn("[dry run]", output)
        self.assertFalse(Trade.objects.exists())

    def test_seed_touches_no_accounts(self):
        from django.contrib.auth import get_user_model

        seed()
        self.assertFalse(get_user_model().objects.exists())


class CatalogApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.client = APIClient()

    def get(self, name, **params):
        response = self.client.get(reverse(name), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_trades_are_public_ordered_and_bilingual(self):
        body = self.get("catalog-trades")
        self.assertEqual(set(body), {"count", "next", "previous", "results"})
        self.assertEqual([t["code"] for t in body["results"]], ["electrician", "plumber", "ac_technician"])
        electrician = body["results"][0]
        self.assertEqual(electrician["labels"], {"ur": "الیکٹریشن", "en": "Electrician"})
        self.assertEqual(electrician["icon"], "zap")
        self.assertEqual(electrician["service_count"], 8)

    def test_inactive_entries_are_hidden(self):
        Trade.objects.filter(code="plumber").update(is_active=False)
        ServiceTag.objects.filter(code="elec_fan_repair").update(is_active=False)
        self.assertNotIn("plumber", [t["code"] for t in self.get("catalog-trades")["results"]])
        services = [s["code"] for s in self.get("catalog-service-tags")["results"]]
        self.assertNotIn("elec_fan_repair", services)
        self.assertFalse(any(code.startswith("plmb_") for code in services))

    def test_service_tag_filters(self):
        plumber = self.get("catalog-service-tags", trade="plumber")
        self.assertEqual(plumber["count"], 8)
        self.assertTrue(all(s["trade"] == "plumber" for s in plumber["results"]))
        both = self.get("catalog-service-tags", trade="plumber,ac_technician")
        self.assertEqual(both["count"], 15)
        self.assertEqual(self.get("catalog-service-tags", trade="unknown")["count"], 0)
        fans = [s["code"] for s in self.get("catalog-service-tags", search="fan")["results"]]
        self.assertEqual(fans, ["elec_fan_install", "elec_fan_repair"])
        urdu = [s["code"] for s in self.get("catalog-service-tags", search="پنکھے")["results"]]
        self.assertEqual(urdu, ["elec_fan_install", "elec_fan_repair"])

    def test_areas_and_cities(self):
        self.assertEqual([c["code"] for c in self.get("catalog-cities")["results"]], ["islamabad", "rawalpindi"])
        rawalpindi = self.get("catalog-areas", city="rawalpindi")
        self.assertEqual(rawalpindi["count"], 8)
        self.assertTrue(all(a["city"]["code"] == "rawalpindi" for a in rawalpindi["results"]))
        sectors = self.get("catalog-areas", kind="sector")["results"]
        self.assertTrue(sectors and all(a["kind"] == "sector" for a in sectors))
        g9 = self.get("catalog-areas", search="G-9")["results"]
        self.assertEqual([a["code"] for a in g9], ["isb-g-9"])
        self.assertIsNone(g9[0]["centre"])  # coordinates not seeded until verified

    def test_pagination(self):
        page = self.get("catalog-areas", page_size=5)
        self.assertEqual(len(page["results"]), 5)
        self.assertEqual(page["count"], 19)
        self.assertIsNotNone(page["next"])

    def test_speciality_questions_for_trade(self):
        body = self.client.get(reverse("catalog-trade-questions", args=["electrician"])).json()
        self.assertEqual(body["trade"]["code"], "electrician")
        self.assertEqual(
            [q["code"] for q in body["questions"]],
            ["services_offered", "primary_specialities", "services_not_offered"],
        )
        first = body["questions"][0]
        self.assertEqual(first["prompt"]["ur"], "آپ الیکٹریشن کی کون سی خدمات فراہم کرتے ہیں؟")
        self.assertEqual(first["prompt"]["en"], "Which Electrician services do you offer?")
        # One main speciality (M4).
        self.assertEqual(body["questions"][1]["selection"], {"multiple": False, "min": 1, "max": 1, "choices_from": "services_offered"})
        self.assertEqual(len(body["choices"]), 8)
        self.assertTrue(all(c["trade"] == "electrician" for c in body["choices"]))
        self.assertEqual({r["type"] for r in body["rules"]}, {"disjoint", "subset"})

    def test_speciality_questions_unknown_trade(self):
        response = self.client.get(reverse("catalog-trade-questions", args=["astronaut"]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")


class SpecialityRuleTests(SimpleTestCase):
    allowed = {"a", "b", "c", "d"}

    def test_consistent_answers(self):
        answers = {"services_offered": {"a", "b"}, "primary_specialities": {"a"}, "services_not_offered": {"c"}}
        self.assertEqual(validate_speciality_answers(answers, self.allowed), [])

    def test_conflicts(self):
        answers = {"services_offered": {"a", "b"}, "primary_specialities": {"c"}, "services_not_offered": {"b", "z"}}
        codes = {c["code"]: c["services"] for c in validate_speciality_answers(answers, self.allowed)}
        self.assertEqual(codes["offered_and_excluded_overlap"], ["b"])
        self.assertEqual(codes["primary_not_offered"], ["c"])
        self.assertEqual(codes["unknown_service"], ["z"])

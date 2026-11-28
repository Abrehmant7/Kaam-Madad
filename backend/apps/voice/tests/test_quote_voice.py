"""The worker's quote answered by voice (kind ``quote_terms``): suggestions only, never a sent quote.

Fixture providers: the speech-to-text fixture returns the Urdu rehearsal sentence for this purpose ("Rs. 1,200 for
labour, the customer provides the materials, and I can work Friday from 4 to 6 PM"); the interpretation fixture is
keyword rules. Live providers are exercised separately (``check_ai_providers --only quote_terms``).
"""

from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.urls import reverse

from apps.conversations.models import Quote
from apps.providers.errors import ProviderInvalidOutput
from apps.voice import drafts
from apps.voice.models import Interpretation

from .test_voice_api import VoiceApiTestCase

KARACHI = ZoneInfo("Asia/Karachi")
SATURDAY = datetime(2026, 11, 28, 10, 0, tzinfo=KARACHI)  # the next Friday is 4 December 2026
FRIDAY = datetime(2026, 12, 4, 10, 0, tzinfo=KARACHI)


def raw(**values):
    base = {key: None for key in drafts.RAW_KEYS["quote_terms"]}
    base["uncertain_fields"] = []
    return {**base, **values}


class QuoteVoiceTests(VoiceApiTestCase):
    def suggestion(self, now=SATURDAY) -> dict:
        with mock.patch("apps.voice.drafts.timezone.now", return_value=now):
            clip = self.upload(purpose="quote_terms")
            self.assertEqual(clip.status_code, 201, clip.content)
            transcription = self.transcribe(clip.json()["id"])
            self.assertEqual(transcription.status_code, 200, transcription.content)
            response = self.interpret(kind="quote_terms", transcription_id=transcription.json()["id"], language="mixed")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_urdu_rehearsal_prefills_only_the_stated_terms(self):
        result = self.suggestion()
        self.assertTrue(result["simulated"])
        fields = result["effective_fields"]
        self.assertEqual(fields["labour_amount"], 1200)
        self.assertEqual(fields["materials"], "customer")
        self.assertEqual(fields["date"], "2026-12-04")  # "جمعہ" said on a Saturday: the coming Friday
        self.assertEqual((fields["start_time"], fields["end_time"]), ("16:00", "18:00"))  # "شام 4 سے 6 بجے"
        # Nothing unstated is filled: no scope, basis, quantity or materials charge.
        self.assertEqual((fields["scope"], fields["labour_basis"], fields["quantity"], fields["materials_amount"]), (None, None, None, None))
        self.assertEqual(result["draft"]["missing"], ["scope"])
        self.assertEqual(result["draft"]["uncertain"], [])
        # A suggestion only: no quote or draft quote exists.
        self.assertFalse(Quote.objects.exists())

    def test_a_weekday_said_on_that_same_weekday_is_left_for_the_worker(self):
        result = self.suggestion(now=FRIDAY)  # "Friday" on a Friday: today or next week?
        self.assertIsNone(result["effective_fields"]["date"])
        self.assertIn("date", result["draft"]["uncertain"])
        self.assertEqual(result["draft"]["heard"]["date"], "جمعہ")
        self.assertEqual(result["effective_fields"]["labour_amount"], 1200)  # the clear terms are still suggested

    def test_a_time_without_morning_or_evening_is_not_guessed(self):
        with mock.patch("apps.voice.drafts.timezone.now", return_value=SATURDAY):
            result = self.interpret(kind="quote_terms", language="ur", text="مزدوری 800 روپے ہوں گے۔ میں 4 سے 6 بجے آ سکتا ہوں۔").json()
        fields = result["effective_fields"]
        self.assertEqual(fields["labour_amount"], 800)
        self.assertEqual((fields["start_time"], fields["end_time"]), (None, None))
        self.assertEqual(set(result["draft"]["uncertain"]) & {"start_time", "end_time"}, {"start_time", "end_time"})

    def test_english_input_is_understood(self):
        with mock.patch("apps.voice.drafts.timezone.now", return_value=SATURDAY):
            result = self.interpret(kind="quote_terms", language="en",
                                    text="Rs. 1,200 for labour, the customer provides the materials, and I can work Friday from 4 to 6 PM.").json()
        fields = result["effective_fields"]
        self.assertEqual((fields["labour_amount"], fields["materials"], fields["date"], fields["start_time"], fields["end_time"]),
                         (1200, "customer", "2026-12-04", "16:00", "18:00"))

    def test_the_same_words_on_another_day_are_interpreted_again(self):
        text = "مزدوری 1000 روپے۔ میں جمعہ کو شام 5 سے 7 بجے آؤں گا۔"
        with mock.patch("apps.voice.drafts.timezone.now", return_value=SATURDAY):
            first = self.interpret(kind="quote_terms", language="ur", text=text).json()
        with mock.patch("apps.voice.drafts.timezone.now", return_value=datetime(2026, 12, 5, 10, 0, tzinfo=KARACHI)):
            later = self.interpret(kind="quote_terms", language="ur", text=text).json()
        self.assertEqual(first["effective_fields"]["date"], "2026-12-04")
        self.assertEqual(later["effective_fields"]["date"], "2026-12-11")  # never a stale, reused date
        self.assertFalse(later["reused"])

    def test_corrections_are_validated(self):
        result = self.suggestion()
        url = reverse("interpretation", args=[result["id"]])
        bad = self.client.patch(url, {"fields": {"materials": "free", "start_time": "25:00"}}, format="json")
        self.assertEqual(bad.status_code, 400)
        good = self.client.patch(url, {"fields": {"scope": "دو پنکھے لگانا", "labour_basis": "total"}}, format="json")
        self.assertEqual(good.status_code, 200, good.content)
        self.assertEqual(good.json()["effective_fields"]["scope"], "دو پنکھے لگانا")
        self.assertEqual(Interpretation.objects.get(pk=result["id"]).draft["fields"]["scope"], None)  # the draft is kept apart


class QuoteDraftRuleTests(VoiceApiTestCase):
    def build(self, **values):
        with mock.patch("apps.voice.drafts.timezone.now", return_value=SATURDAY):
            return drafts.build_draft("quote_terms", drafts.validate_raw("quote_terms", raw(**values)), "", drafts.CatalogIndex.load())

    def test_invalid_model_output_is_rejected(self):
        with self.assertRaises(ProviderInvalidOutput):
            drafts.validate_raw("quote_terms", raw(labour_amount_pkr="1200"))  # a string where a number is required
        with self.assertRaises(ProviderInvalidOutput):
            drafts.validate_raw("quote_terms", {"labour_amount_pkr": 1200})  # keys missing

    def test_unclear_or_conflicting_values_stay_empty(self):
        draft = self.build(materials="free", appointment_weekday="friday", appointment_relative_day="tomorrow",
                           start_time="18:00", end_time="16:00", materials_amount_pkr=500, labour_amount_pkr=-5)
        fields = draft["fields"]
        self.assertEqual((fields["materials"], fields["date"], fields["start_time"], fields["end_time"]), (None, None, None, None))
        self.assertIsNone(fields["materials_amount"])  # a charge without "worker brings them, charged separately"
        self.assertIsNone(fields["labour_amount"])
        self.assertTrue({"materials", "date", "start_time", "end_time", "materials_amount", "labour_amount"} <= set(draft["uncertain"]))

    def test_explicit_relative_and_far_dates(self):
        self.assertEqual(self.build(appointment_relative_day="tomorrow")["fields"]["date"], "2026-11-29")
        self.assertEqual(self.build(appointment_date="2026-12-10")["fields"]["date"], "2026-12-10")
        far = self.build(appointment_date="2027-06-01")  # beyond 90 days: the quote rules would refuse it
        self.assertIsNone(far["fields"]["date"])
        self.assertIn("date", far["uncertain"])
        worker_brings = self.build(materials="worker_extra", materials_amount_pkr=1500, labour_basis="per_item", quantity=2)
        self.assertEqual((worker_brings["fields"]["materials"], worker_brings["fields"]["materials_amount"]), ("worker_extra", 1500))
        self.assertNotIn("quantity", worker_brings["missing"])

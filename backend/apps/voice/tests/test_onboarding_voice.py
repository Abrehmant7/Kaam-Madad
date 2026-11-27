"""'Answer by voice' on worker signup screens 2 and 3 (pitch item 2): suggestions only, manual path always works."""

from unittest import mock

from django.test import override_settings
from django.urls import reverse

from apps.voice import drafts
from apps.workers.tests.helpers import GOOD_AREAS, GOOD_WORK

from .test_voice_api import VoiceApiTestCase


class OnboardingVoiceTests(VoiceApiTestCase):
    def voice_suggestion(self, kind: str) -> dict:
        clip = self.upload(purpose=kind)
        self.assertEqual(clip.status_code, 201, clip.content)
        transcription = self.transcribe(clip.json()["id"])
        self.assertEqual(transcription.status_code, 200, transcription.content)
        response = self.interpret(kind=kind, transcription_id=transcription.json()["id"], language="mixed")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_work_step_suggestions_respect_negation_and_the_main_speciality(self):
        draft = self.voice_suggestion("onboarding_work")
        fields = draft["effective_fields"]
        self.assertEqual(fields["trade"], "electrician")
        self.assertEqual(sorted(fields["services_offered"]), ["elec_fan_install", "elec_wiring_repair"])
        self.assertEqual(fields["services_not_offered"], ["elec_ups_inverter"])  # "UPS کا کام نہیں کرتا"
        self.assertEqual(fields["primary_specialities"], ["elec_fan_install"])
        self.assertTrue(draft["simulated"])
        # The worker still confirms by saving the screen; nothing was saved by the voice answer.
        self.assertIsNone(self.client.get(reverse("worker-me")).json()["profile"]["trade"])

    def test_areas_step_suggestions_leave_out_negated_areas(self):
        draft = self.voice_suggestion("onboarding_areas")
        self.assertEqual(draft["effective_fields"]["city"], "islamabad")
        self.assertCountEqual(draft["effective_fields"]["service_areas"], ["isb-g-9", "isb-g-10"])
        self.assertEqual(draft["draft"]["not_selected"], ["isb-f-8"])

    def test_ambiguous_choices_stay_unselected(self):
        catalog = drafts.CatalogIndex.load()
        two_mains = self.interpret(kind="onboarding_work", language="ur",
                                   text="میں پنکھے لگاتا ہوں اور wiring ٹھیک کرتا ہوں۔ میرا خاص کام پنکھے لگانا اور wiring ہے۔").json()
        self.assertEqual(two_mains["effective_fields"]["primary_specialities"], [])
        self.assertIn("primary_specialities", two_mains["draft"]["uncertain"])
        not_offered_main = drafts.build_draft("onboarding_work", {
            "trade": "electrician", "service_mentions": [{"phrase": "fans", "service_code": "elec_fan_install", "negated": False}],
            "main_speciality_code": "elec_wiring_repair", "uncertain_fields": []}, "", catalog)
        self.assertEqual(not_offered_main["fields"]["primary_specialities"], [])
        two_cities = drafts.build_draft("onboarding_areas", {"city_code": None, "uncertain_fields": [], "area_mentions": [
            {"phrase": "G-9", "area_code": "isb-g-9", "negated": False},
            {"phrase": "Saddar", "area_code": "rwp-saddar", "negated": False}]}, "", catalog)
        self.assertEqual(two_cities["fields"], {"city": None, "service_areas": []})
        self.assertIn("city", two_cities["uncertain"])
        said_both = drafts.build_draft("onboarding_work", {"trade": None, "main_speciality_code": None, "uncertain_fields": [],
                                                           "service_mentions": [
            {"phrase": "fans", "service_code": "elec_fan_install", "negated": False},
            {"phrase": "no fans", "service_code": "elec_fan_install", "negated": True}]}, "", catalog)
        self.assertEqual((said_both["fields"]["services_offered"], said_both["fields"]["services_not_offered"]), ([], []))

    def test_unknown_codes_from_the_model_are_never_suggested(self):
        catalog = drafts.CatalogIndex.load()
        draft = drafts.build_draft("onboarding_areas", {"city_code": "lahore", "uncertain_fields": [], "area_mentions": [
            {"phrase": "Model Town", "area_code": "lhr-model-town", "negated": False}]}, "", catalog)
        self.assertEqual(draft["fields"], {"city": None, "service_areas": []})
        self.assertEqual(draft["unmatched_mentions"], [{"phrase": "Model Town", "negated": False}])

    @override_settings(SPEECH_TO_TEXT_PROVIDER="elevenlabs", ELEVENLABS_API_KEY="test-key", AI_PROVIDER_MAX_RETRIES=0)
    def test_scribe_urdu_fallback_result_is_reused_for_the_same_clip(self):
        import httpx

        from apps.providers import http as provider_http

        replies = [{"text": "मैं पंखे लगाता हूँ"}, {"text": "میں پنکھے لگاتا ہوں"}]
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(200, json=replies[len(calls) - 1])

        clip = self.upload(purpose="onboarding_work").json()
        with mock.patch.object(provider_http, "default_client", return_value=httpx.Client(transport=httpx.MockTransport(handler))):
            first = self.transcribe(clip["id"]).json()
            again = self.transcribe(clip["id"]).json()
        self.assertEqual((first["text"], first["model"], first["reused"]), ("میں پنکھے لگاتا ہوں", "scribe_v2", False))
        self.assertTrue(again["reused"])
        self.assertEqual(len(calls), 2)  # v3 + one fallback; the second request is served from the stored transcript

    @override_settings(SPEECH_TO_TEXT_PROVIDER="unconfigured", INTERPRETATION_PROVIDER="unconfigured")
    def test_manual_onboarding_survives_provider_failure(self):
        clip = self.upload(purpose="onboarding_work").json()
        self.assertEqual(self.transcribe(clip["id"]).status_code, 503)
        self.assertEqual(self.interpret(kind="onboarding_work", text="میں الیکٹریشن ہوں", language="ur").status_code, 503)
        self.assertEqual(self.client.put(reverse("worker-work"), GOOD_WORK, format="json").status_code, 200)
        saved = self.client.put(reverse("worker-areas"), GOOD_AREAS, format="json")
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertTrue(saved.json()["onboarding"]["complete"])

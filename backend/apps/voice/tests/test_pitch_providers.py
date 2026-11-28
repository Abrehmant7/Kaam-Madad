"""Pitch providers against mocked HTTP: ElevenLabs Scribe speech-to-text, Groq interpretation and agreement check.

No network and no credentials. The documented request/response shapes are checked here; live behaviour is checked
with ``python manage.py check_ai_providers`` (README "Pitch configuration").
"""

import json
from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings

from apps.providers import http as provider_http
from apps.providers import registry
from apps.providers.agreement import (
    MERGE_RULE,
    FixtureAgreementChecker,
    GroqAgreementChecker,
    conversation_language,
    grounded_findings,
)
from apps.providers.errors import ProviderInvalidOutput, ProviderLimitReached, ProviderNotConfigured, ProviderUnavailable
from apps.providers.groq import strict_schema
from apps.providers.interpretation import RAW_SCHEMAS, FixtureInterpretation, GroqInterpretation
from apps.providers.speech_to_text import ElevenLabsSpeechToText, spoken_language
from apps.voice.management.commands.check_ai_providers import AGREEMENT_SCENARIOS

ELEVEN = {"ELEVENLABS_API_KEY": "test-eleven-key", "ELEVENLABS_STT_MODEL": "scribe_v3", "AI_PROVIDER_MAX_RETRIES": 1}
GROQ = {"GROQ_API_KEY": "test-groq-key", "GROQ_INTERPRETATION_MODEL": "openai/gpt-oss-120b",
        "GROQ_AGREEMENT_MODEL": "openai/gpt-oss-120b", "AI_PROVIDER_MAX_RETRIES": 1}
SCENARIOS = {label: (sample, expected) for label, sample, expected in AGREEMENT_SCENARIOS}


def client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def groq_reply(payload: dict, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(200, json={"id": "c1", "object": "chat.completion", "choices": [
        {"index": 0, "finish_reason": finish_reason,
         "message": {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)}},
    ]})


class NoSleep(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch.object(provider_http, "_sleep")
        patcher.start()
        self.addCleanup(patcher.stop)


@override_settings(**ELEVEN)
class ElevenLabsScribeTests(NoSleep):
    def test_request_shape_and_mixed_urdu_english_transcript(self):
        seen = {}

        def handler(request: httpx.Request):
            seen["url"], seen["headers"], seen["body"] = str(request.url), request.headers, request.content
            return httpx.Response(200, json={"language_code": "urd", "language_probability": 0.97,
                                             "text": "میں  motor rewinding نہیں کرتا", "words": []})

        result = ElevenLabsSpeechToText(client=client_with(handler)).transcribe(
            audio=b"RIFF....WAVEfake", mime_type="audio/wav", language_hint="ur", purpose="onboarding_work")
        self.assertEqual(seen["url"], "https://api.elevenlabs.io/v1/speech-to-text")
        self.assertEqual(seen["headers"]["xi-api-key"], "test-eleven-key")
        self.assertTrue(seen["headers"]["content-type"].startswith("multipart/form-data"))
        body = seen["body"].decode("latin-1")
        for part in ('name="model_id"', "scribe_v3", 'name="language_code"', 'name="file"; filename="clip.wav"',
                     'name="tag_audio_events"'):
            self.assertIn(part, body)
        self.assertEqual((result.text, result.language, result.no_speech), ("میں motor rewinding نہیں کرتا", "mixed", False))
        self.assertEqual((result.provider, result.model, result.simulated), ("elevenlabs", "scribe_v3", False))

    def test_auto_hint_lets_scribe_detect_and_english_is_english(self):
        seen = {}

        def handler(request):
            seen["body"] = request.content.decode("latin-1")
            return httpx.Response(200, json={"language_code": "eng", "language_probability": 0.9, "text": "Two fans please.", "words": []})

        result = ElevenLabsSpeechToText(client=client_with(handler)).transcribe(
            audio=b"x" * 100, mime_type="audio/mpeg", language_hint="auto", purpose="job_description")
        self.assertNotIn('name="language_code"', seen["body"])
        self.assertIn('filename="clip.mp3"', seen["body"])
        self.assertEqual(result.language, "en")

    def test_silence_is_no_speech_and_hindi_script_for_urdu_is_refused(self):
        silent = ElevenLabsSpeechToText(client=client_with(lambda r: httpx.Response(200, json={"text": "", "language_code": "urd"})))
        self.assertTrue(silent.transcribe(audio=b"x", mime_type="audio/wav", language_hint="ur", purpose="review").no_speech)
        devanagari = ElevenLabsSpeechToText(client=client_with(lambda r: httpx.Response(200, json={"text": "मैं पंखे लगाता हूँ"})))
        with self.assertRaises(ProviderInvalidOutput) as ctx:
            devanagari.transcribe(audio=b"x", mime_type="audio/wav", language_hint="ur", purpose="review")
        self.assertEqual(ctx.exception.reason, "transcript_wrong_script")

    def test_devanagari_from_scribe_v3_is_retried_once_with_the_urdu_fallback(self):
        forms = []
        replies = [{"text": "मैं electrician हूँ, UPS का काम नहीं करता।", "language_code": "urd"},
                   {"text": "میں electrician ہوں، UPS کا کام نہیں کرتا۔", "language_code": "urd"}]

        def handler(request):
            forms.append(request.content.decode("utf-8", "replace"))
            return httpx.Response(200, json=replies[len(forms) - 1])

        result = ElevenLabsSpeechToText(client=client_with(handler)).transcribe(
            audio=b"x", mime_type="audio/wav", language_hint="ur", purpose="onboarding_work")
        self.assertEqual(len(forms), 2)
        self.assertIn("scribe_v3", forms[0])
        self.assertIn("scribe_v2", forms[1])
        self.assertIn('name="language_code"\r\n\r\nur', forms[1])
        self.assertEqual((result.text, result.model, result.language), ("میں electrician ہوں، UPS کا کام نہیں کرتا۔", "scribe_v2", "mixed"))

    def test_no_fallback_for_an_english_hint_or_when_disabled(self):
        calls = []

        def devanagari(request):
            calls.append(1)
            return httpx.Response(200, json={"text": "मैं पंखे लगाता हूँ"})

        with self.assertRaises(ProviderInvalidOutput):
            ElevenLabsSpeechToText(client=client_with(devanagari)).transcribe(audio=b"x", mime_type="audio/wav", language_hint="en", purpose="message")
        self.assertEqual(len(calls), 1)
        with override_settings(ELEVENLABS_STT_URDU_FALLBACK_MODEL=""):
            with self.assertRaises(ProviderInvalidOutput):
                ElevenLabsSpeechToText(client=client_with(devanagari)).transcribe(audio=b"x", mime_type="audio/wav", language_hint="ur", purpose="message")
        self.assertEqual(len(calls), 2)

    def test_error_mapping_preserves_the_taxonomy(self):
        cases = [
            (httpx.Response(401, json={"detail": {"status": "quota_exceeded"}}), ProviderLimitReached, "quota_exceeded"),
            (httpx.Response(401, json={"detail": {"status": "missing_permissions"}}), ProviderNotConfigured, "missing_permissions"),
            (httpx.Response(401, json={"detail": {"status": "invalid_api_key"}}), ProviderNotConfigured, "credentials_rejected"),
            (httpx.Response(429, json={}), ProviderLimitReached, "provider_rate_limited"),
            (httpx.Response(503), ProviderUnavailable, "http_503"),
            (httpx.Response(200, text="not json"), ProviderInvalidOutput, "response_not_json"),
        ]
        for response, error, reason in cases:
            with self.subTest(reason=reason):
                provider = ElevenLabsSpeechToText(client=client_with(lambda r, resp=response: resp))
                with self.assertRaises(error) as ctx:
                    provider.transcribe(audio=b"x", mime_type="audio/wav", language_hint="ur", purpose="message")
                self.assertEqual(ctx.exception.reason, reason)

    def test_timeouts_are_retried_within_the_bound(self):
        calls = []

        def handler(request):
            calls.append(1)
            raise httpx.ReadTimeout("slow")

        with self.assertRaises(ProviderUnavailable):
            ElevenLabsSpeechToText(client=client_with(handler)).transcribe(audio=b"x", mime_type="audio/wav", language_hint="ur", purpose="message")
        self.assertEqual(len(calls), 2)  # one try + AI_PROVIDER_MAX_RETRIES=1

    @override_settings(ELEVENLABS_API_KEY="")
    def test_missing_key(self):
        with self.assertRaises(ProviderNotConfigured):
            ElevenLabsSpeechToText()

    def test_spoken_language(self):
        self.assertEqual(spoken_language("kal shaam aa jayen", "urd"), "ur")  # Roman Urdu
        self.assertEqual(spoken_language("پنکھا لگانا ہے", None), "ur")
        self.assertEqual(spoken_language("fan", "eng"), "en")


@override_settings(**GROQ)
class GroqInterpretationTests(NoSleep):
    RAW = {"description": "جی-9 میں دو چھت کے پنکھے لگانے ہیں۔ اے سی کی سروس نہیں چاہیے۔", "trade": "electrician",
           "service_mentions": [{"phrase": "install two ceiling fans", "service_code": "elec_fan_install", "negated": False},
                                {"phrase": "No AC service", "service_code": "ac_service_cleaning", "negated": True}],
           "area_phrase": "G-9", "area_code": "isb-g-9", "preferred_time_text": "tomorrow evening", "budget_pkr": None,
           "uncertain_fields": ["preferred_time_text"]}

    def test_strict_json_schema_request_and_parsing(self):
        seen = {}

        def handler(request):
            seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], json.loads(request.content)
            return groq_reply(self.RAW)

        result = GroqInterpretation(client=client_with(handler)).interpret(
            kind="job_description", text="Please install two ceiling fans in G-9 tomorrow evening. No AC service.",
            language="en", catalog={"trades": [], "services": [], "areas": []})
        body = seen["body"]
        self.assertEqual(seen["url"], "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(seen["auth"], "Bearer test-groq-key")
        self.assertEqual(body["model"], "openai/gpt-oss-120b")
        self.assertEqual(body["response_format"]["type"], "json_schema")
        schema = body["response_format"]["json_schema"]
        self.assertTrue(schema["strict"])
        self.assertFalse(schema["schema"]["additionalProperties"])
        self.assertEqual(set(schema["schema"]["required"]), set(RAW_SCHEMAS["job_description"]["properties"]))
        item = schema["schema"]["properties"]["service_mentions"]["items"]
        self.assertFalse(item["additionalProperties"])
        self.assertEqual((body["reasoning_effort"], body["include_reasoning"]), ("low", False))
        user = body["messages"][1]["content"]
        self.assertIn("faithful Urdu", user)
        self.assertIn("<<<\nPlease install two ceiling fans", user)
        self.assertEqual((result.provider, result.model, result.raw), ("groq", "openai/gpt-oss-120b", self.RAW))

    def test_errors_and_invalid_output(self):
        cases = [
            (httpx.Response(429, json={"error": {"message": "rate", "type": "rate_limit"}}), ProviderLimitReached),
            (httpx.Response(498, json={"error": {"message": "flex"}}), ProviderLimitReached),
            (httpx.Response(401, json={"error": {"message": "bad key"}}), ProviderNotConfigured),
            (httpx.Response(400, json={"error": {"message": "x", "code": "json_validate_failed"}}), ProviderInvalidOutput),
            (httpx.Response(503), ProviderUnavailable),
            (groq_reply(self.RAW, finish_reason="length"), ProviderInvalidOutput),
            (httpx.Response(200, json={"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]}), ProviderInvalidOutput),
            (httpx.Response(200, json={"choices": []}), ProviderInvalidOutput),
        ]
        for response, error in cases:
            with self.subTest(status=response.status_code, error=error.__name__):
                provider = GroqInterpretation(client=client_with(lambda r, resp=response: resp))
                with self.assertRaises(error):
                    provider.interpret(kind="job_description", text="x", language="en", catalog={})

    @override_settings(GROQ_API_KEY="")
    def test_missing_key_means_not_configured_and_no_gemini_key_is_needed(self):
        with self.assertRaises(ProviderNotConfigured):
            GroqInterpretation()

    def test_strict_schema_helper_does_not_change_the_original(self):
        original = RAW_SCHEMAS["onboarding_areas"]
        strict = strict_schema(original)
        self.assertNotIn("additionalProperties", original)
        self.assertFalse(strict["properties"]["area_mentions"]["items"]["additionalProperties"])
        self.assertEqual(strict["properties"]["area_mentions"]["items"]["required"], ["phrase", "area_code", "negated"])


@override_settings(**GROQ)
class GroqAgreementTests(NoSleep):
    def check(self, label, findings):
        sample, _ = SCENARIOS[label]
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.content)
            return groq_reply({"findings": findings})

        result = GroqAgreementChecker(client=client_with(handler)).check(**sample)
        return result, seen["body"]

    def test_pitch_materials_findings_are_merged_into_exactly_one(self):
        findings = [
            {"code": "materials_responsibility", "ask": "worker", "question": "Who buys the fans and wiring?",
             "sources": [{"kind": "request", "ref": "description", "text": "Rs. 1,200 including materials"},
                         {"kind": "quote", "ref": "materials", "text": "customer"}]},
            {"code": "materials_responsibility", "ask": "customer", "question": "Will you buy the materials?",
             "sources": [{"kind": "message", "ref": "m2", "text": "You will buy the fans and wiring yourself."}]},
        ]
        result, body = self.check("pitch_v1_labour_only", findings)
        self.assertEqual([f["code"] for f in result.findings], ["materials_responsibility"])
        merged = result.findings[0]
        self.assertEqual((merged["ask"], merged["question"]), ("both", "Who buys the fans and wiring?"))
        self.assertEqual(len(merged["sources"]), 3)
        self.assertIn(MERGE_RULE, body["messages"][0]["content"])
        self.assertEqual((body["reasoning_effort"], body["max_completion_tokens"], body["temperature"]), ("high", 3500, 0.2))
        self.assertIn("'included' = the worker supplies the materials", body["messages"][0]["content"])
        payload = json.loads(body["messages"][1]["content"])
        self.assertEqual(payload["conversation_language"], "English")
        self.assertEqual(payload["quote"]["materials"], "customer")

    def test_messages_are_numbered_and_the_quote_comes_after_them(self):
        _, body = self.check("pitch_v2_materials_included", [])
        payload = json.loads(body["messages"][1]["content"])
        self.assertEqual([m["order"] for m in payload["messages"]], [1, 2, 3])
        self.assertEqual(payload["quote"]["sent_after_message"], 3)
        self.assertIn("LATEST", body["messages"][0]["content"])

    def test_a_schema_rejection_at_high_effort_is_retried_once_at_medium(self):
        sample, _ = SCENARIOS["pitch_v1_labour_only"]
        efforts = []

        def handler(request):
            efforts.append(json.loads(request.content)["reasoning_effort"])
            if len(efforts) == 1:
                return httpx.Response(400, json={"error": {"message": "Failed to validate JSON", "type": "invalid_request_error",
                                                           "code": "json_validate_failed"}})
            return groq_reply({"findings": []})

        result = GroqAgreementChecker(client=client_with(handler)).check(**sample)
        self.assertEqual((efforts, result.findings), (["high", "medium"], []))
        failing = GroqAgreementChecker(client=client_with(lambda r: httpx.Response(
            400, json={"error": {"message": "x", "code": "json_validate_failed"}})))
        with self.assertRaises(ProviderInvalidOutput):  # still invalid after the one retry: "could not run"
            failing.check(**sample)

    def test_revised_quote_with_no_findings_passes(self):
        result, _ = self.check("pitch_v2_materials_included", [])
        self.assertEqual(result.findings, [])

    def test_roman_urdu_question_language_is_requested(self):
        _, body = self.check("roman_urdu_labour_only", [
            {"code": "materials_responsibility", "ask": "worker", "question": "Saman kaun laye ga?",
             "sources": [{"kind": "request", "ref": "description", "text": "1200 rupay saman samet"}]}])
        self.assertIn("Roman Urdu", json.loads(body["messages"][1]["content"])["conversation_language"])

    def test_separate_timing_disagreement_stays_a_second_finding(self):
        result, _ = self.check("separate_timing_disagreement", [
            {"code": "materials_responsibility", "ask": "worker", "question": "Who supplies the materials?",
             "sources": [{"kind": "request", "ref": "description", "text": "including materials"}]},
            {"code": "timing_mismatch", "ask": "both", "question": "Is 10 am or 5 pm correct?",
             "sources": [{"kind": "message", "ref": "m1", "text": "Please come at 5 pm"},
                         {"kind": "quote", "ref": "start_at", "text": "2030-01-10T10:00+05:00"}]},
        ])
        self.assertEqual(sorted(f["code"] for f in result.findings), ["materials_responsibility", "timing_mismatch"])

    def test_ungrounded_answer_is_refused_never_clean(self):
        with self.assertRaises(ProviderInvalidOutput) as ctx:
            self.check("pitch_v1_labour_only", [
                {"code": "materials_responsibility", "ask": "worker", "question": "?",
                 "sources": [{"kind": "message", "ref": "m2", "text": "I will bring everything"}]}])
        self.assertEqual(ctx.exception.reason, "findings_ungrounded")
        with self.assertRaises(ProviderInvalidOutput):
            grounded_findings([{"code": "made_up", "ask": "x", "question": "?", "sources": []}], {}, [], {})

    def test_rate_limit_is_an_error_not_a_result(self):
        checker = GroqAgreementChecker(client=client_with(lambda r: httpx.Response(429, json={})))
        with self.assertRaises(ProviderLimitReached):
            checker.check(**SCENARIOS["pitch_v1_labour_only"][0])


class FixturePitchTests(SimpleTestCase):
    """The simulated checker (demo/tests) on the exact pitch example."""

    def test_pitch_example_and_revision(self):
        checker = FixtureAgreementChecker()
        for label in ("urdu_m7_sample", "pitch_v1_labour_only", "pitch_v2_materials_included", "roman_urdu_labour_only"):
            sample, expected = SCENARIOS[label]
            with self.subTest(label=label):
                self.assertEqual([f["code"] for f in checker.check(**sample).findings], expected)

    def test_question_follows_roman_urdu(self):
        finding = FixtureAgreementChecker().check(**SCENARIOS["roman_urdu_labour_only"][0]).findings[0]
        self.assertIn("Saman kaun", finding["question"])
        self.assertEqual(conversation_language({"description": "Two fans please"}, []), "en")

    def test_english_job_gets_a_simulated_urdu_description_and_respects_negation(self):
        catalog = {
            "trades": [{"code": "electrician", "en": "Electrician", "ur": "الیکٹریشن"}],
            "services": [{"code": "elec_fan_install", "trade": "electrician", "en": "Ceiling fan installation", "ur": "چھت کے پنکھے کی تنصیب"},
                         {"code": "ac_service_cleaning", "trade": "ac_technician", "en": "AC service", "ur": "اے سی کی سروس اور صفائی"}],
            "areas": [{"code": "isb-g-9", "city": "islamabad", "en": "G-9", "ur": "جی-9"}],
        }
        raw = FixtureInterpretation().interpret(
            kind="job_description", text="Please install two ceiling fans in G-9 tomorrow evening. No AC service needed.",
            language="en", catalog=catalog).raw
        self.assertEqual((raw["trade"], raw["area_code"]), ("electrician", "isb-g-9"))
        self.assertIn({"phrase": "No AC service needed", "service_code": "ac_service_cleaning", "negated": True}, raw["service_mentions"])
        self.assertIn("چھت کے پنکھے کی تنصیب", raw["description"])
        self.assertIn("نہیں چاہیے", raw["description"])


class PitchConfigurationTests(SimpleTestCase):
    @override_settings(SPEECH_TO_TEXT_PROVIDER="elevenlabs", INTERPRETATION_PROVIDER="groq", AGREEMENT_CHECK_PROVIDER="groq",
                       TEXT_TO_SPEECH_PROVIDER="elevenlabs", ELEVENLABS_API_KEY="k", ELEVENLABS_VOICE_ID="JBFqnCBsd6RMkjVDRZzb",
                       GROQ_API_KEY="g", GEMINI_API_KEY="")
    def test_pitch_configuration_is_fully_available_without_gemini(self):
        status = registry.status()
        for capability, provider in (("speech_to_text", "elevenlabs"), ("text_to_speech", "elevenlabs"),
                                     ("interpretation", "groq"), ("agreement_check", "groq")):
            self.assertEqual(status[capability], {"provider": provider, "available": True, "simulated": False}, capability)

    @override_settings(SPEECH_TO_TEXT_PROVIDER="elevenlabs", INTERPRETATION_PROVIDER="groq", ELEVENLABS_API_KEY="", GROQ_API_KEY="")
    def test_missing_keys_report_not_available(self):
        status = registry.status()
        self.assertFalse(status["speech_to_text"]["available"])
        self.assertFalse(status["interpretation"]["available"])

    @override_settings(INTERPRETATION_PROVIDER="gemini", GEMINI_API_KEY="k")
    def test_gemini_stays_selectable(self):
        self.assertEqual(registry.interpretation().name, "gemini")

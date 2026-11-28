"""Exercise each configured AI/audio provider once (live check). Prints no keys.

    python manage.py check_ai_providers --audio path/to/sample.wav [--language ur]
    python manage.py check_ai_providers --only text_to_speech --save-speech speech.mp3
    python manage.py check_ai_providers --only cnic_ocr --cnic-image ../docs/demo/cnic/demo-card-bilal-ahmed.png
    python manage.py check_ai_providers --only agreement_check
    python manage.py check_ai_providers --only interpretation
    python manage.py check_ai_providers --only quote_terms [--audio quote.mp3]

- Speech-to-text runs only with --audio (any supported format, ≤ 60 s, ≤ 10 MB) through the configured
  provider (ElevenLabs Scribe for the pitch configuration).
- Interpretation runs four fictional samples: a worker introduction (the transcript, or a built-in Urdu sample),
  the pitch's ENGLISH job request (expects electrician / ceiling fan installation / G-9, AC service excluded, and
  an Urdu description), and the two worker signup screens answered by voice (work; areas with a negation).
- Text-to-speech reads --speak (default: a fictional Urdu sentence with English trade terms),
  checks that real audio came back, and with --save-speech writes it to a file to listen to.
- CNIC OCR runs the configured OCR provider (Tesseract on this host) on each --cnic-image and prints
  the extracted name and the MASKED number. Use the synthetic DEMO cards in docs/demo/cnic/.
- Agreement check runs the configured checker on fictional scenarios and prints each finding with its verified
  source statements: the Urdu M7 sample and the pitch example (Rs. 1,200 "including materials" vs a labour-only
  quote → exactly one materials finding; revised to labour + materials → no findings), the same in Roman Urdu,
  and a case with a separate timing disagreement that must stay a second finding.
- Quote terms (the worker's quote answered by voice) interprets the Urdu rehearsal sentence "Rs. 1,200 for labour,
  the customer provides the materials, and I can work Friday from 4 to 6 PM" (number words, as spoken) and expects
  1200 / customer / the coming Friday / 16:00–18:00 with every other term left empty. With live speech providers it
  also reads the sentence aloud (text-to-speech), transcribes that audio (speech-to-text) and interprets the
  transcript; with --audio it transcribes your own recording instead.
Each step reports OK, or the error code and reason (not configured / limit / unavailable / invalid output).
Use fictional speech and text only — never real CNIC numbers or personal details.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.providers import registry
from apps.providers.errors import ProviderError, ProviderLimitReached
from apps.providers.text_to_speech import AUDIO_EXTENSIONS
from apps.voice import drafts
from apps.voice.audio import inspect_audio

SAMPLE_TEXT = "میرا نام احمد ہے۔ میں الیکٹریشن ہوں۔ میں پنکھے لگاتا ہوں لیکن motor rewinding نہیں کرتا۔"
SPEECH_SAMPLE = "احمد صاحب کل شام G-9 میں دو پنکھے لگائیں گے۔ AC کی service نہیں ہو گی۔"
STEPS = ("speech_to_text", "interpretation", "text_to_speech", "cnic_ocr", "agreement_check", "quote_terms")
# Fictional: Rs. 1,200 labour, the customer provides the materials, Friday 4–6 PM (number words, as a worker says them).
QUOTE_SAMPLE_UR = "مزدوری کے بارہ سو روپے ہوں گے، سامان گاہک خود دیں گے، اور میں جمعہ کو شام چار سے چھ بجے تک کام کر سکتا ہوں۔"
JOB_SAMPLE_EN = "Please install two ceiling fans at my house in G-9 tomorrow evening. No AC service needed."
WORK_SAMPLE_UR = "میں الیکٹریشن ہوں۔ میں پنکھے لگاتا ہوں اور wiring ٹھیک کرتا ہوں۔ میرا خاص کام پنکھے لگانا ہے۔ UPS کا کام نہیں کرتا۔"
AREAS_SAMPLE_UR = "میں اسلام آباد میں G-9 اور G-10 میں کام کرتا ہوں۔ F-8 نہیں جاتا۔"
_PITCH_REQUEST = {
    "description": "Please install two ceiling fans in G-9 tomorrow evening. My budget is Rs. 1,200 including materials.",
    "trade": "electrician", "services": ["elec_fan_install"], "services_excluded": [], "area": "isb-g-9",
    "window_start": "2030-01-10T17:00+05:00", "window_end": "2030-01-10T19:00+05:00", "budget_preference_pkr": "1200.00",
}
_PITCH_QUOTE = {
    "version": 1, "inspection_only": False, "scope": "Install two ceiling fans", "quantity": 2,
    "labour_amount_pkr": "1200.00", "labour_basis": "total", "materials": "customer", "materials_amount_pkr": None,
    "visit_fee_pkr": None, "visit_fee_treatment": "none", "exclusions": "",
    "start_at": "2030-01-10T17:00+05:00", "end_at": "2030-01-10T19:00+05:00",
}
_PITCH_MESSAGES = [
    {"id": "m1", "role": "customer", "text": "Can you come tomorrow at 5 pm?"},
    {"id": "m2", "role": "worker", "text": "Yes. Rs. 1,200 is for labour only. You will buy the fans and wiring yourself."},
]
_ROMAN_REQUEST = {**_PITCH_REQUEST, "description": "G-9 mein do ceiling fan lagwane hain. 1200 rupay saman samet."}
_ROMAN_MESSAGES = [
    {"id": "m1", "role": "customer", "text": "Kya aap kal shaam 5 baje aa sakte hain?"},
    {"id": "m2", "role": "worker", "text": "Ji, 1200 sirf mazdoori hai. Saman aap khud le kar rakhein."},
]
# Fictional M7 sample: the request includes materials, the worker's message and quote say labour only.
AGREEMENT_SAMPLE = {
    "request": {"description": "دو چھت کے پنکھے لگانے ہیں۔ میرا بجٹ 3500 روپے ہے، سامان سمیت۔", "trade": "electrician",
                "services": ["elec_fan_install"], "services_excluded": [], "area": "isb-g-9",
                "window_start": "2030-01-10T17:00+05:00", "window_end": "2030-01-10T19:00+05:00", "budget_preference_pkr": "3500.00"},
    "messages": [
        {"id": "m1", "role": "customer", "text": "السلام علیکم، کیا آپ کل شام آ سکتے ہیں؟"},
        {"id": "m2", "role": "worker", "text": "جی، کل پانچ بجے آ جاؤں گا۔ پنکھوں کا سامان آپ خود لے کر رکھیں، میں صرف لگاؤں گا۔"},
    ],
    "quote": {"version": 1, "inspection_only": False, "scope": "دو چھت کے پنکھے لگانا", "quantity": 2,
              "labour_amount_pkr": "600.00", "labour_basis": "per_item", "materials": "customer", "materials_amount_pkr": None,
              "visit_fee_pkr": None, "visit_fee_treatment": "none", "exclusions": "",
              "start_at": "2030-01-10T17:00+05:00", "end_at": "2030-01-10T19:00+05:00"},
}
# (label, sample, expected finding codes — order-insensitive)
AGREEMENT_SCENARIOS = [
    ("urdu_m7_sample", AGREEMENT_SAMPLE, ["materials_responsibility"]),
    ("pitch_v1_labour_only", {"request": _PITCH_REQUEST, "messages": _PITCH_MESSAGES, "quote": _PITCH_QUOTE},
     ["materials_responsibility"]),
    ("pitch_v2_materials_included", {
        "request": _PITCH_REQUEST,
        "messages": _PITCH_MESSAGES + [{"id": "m3", "role": "worker", "text": "OK, I will bring the fans and wiring. Rs. 1,200 including materials."}],
        "quote": {**_PITCH_QUOTE, "version": 2, "materials": "included"},
    }, []),
    ("roman_urdu_labour_only", {"request": _ROMAN_REQUEST, "messages": _ROMAN_MESSAGES, "quote": _PITCH_QUOTE},
     ["materials_responsibility"]),
    ("separate_timing_disagreement", {
        "request": _PITCH_REQUEST,
        "messages": [{"id": "m1", "role": "customer", "text": "Please come at 5 pm, I am not home in the morning."},
                     _PITCH_MESSAGES[1]],
        "quote": {**_PITCH_QUOTE, "start_at": "2030-01-10T10:00+05:00", "end_at": "2030-01-10T12:00+05:00"},
    }, ["materials_responsibility", "timing_mismatch"]),
]


def _urdu(text) -> bool:
    return isinstance(text, str) and any("\u0600" <= ch <= "\u06ff" for ch in text)


class Command(BaseCommand):
    help = "Call each configured speech-to-text, interpretation and text-to-speech provider once."

    def add_arguments(self, parser):
        parser.add_argument("--audio", help="Path to a short fictional voice sample to transcribe.")
        parser.add_argument("--language", default="ur", choices=["ur", "en", "auto"])
        parser.add_argument("--only", choices=STEPS, help="Run just one step.")
        parser.add_argument("--speak", default=SPEECH_SAMPLE, help="Fictional text to read aloud.")
        parser.add_argument("--speak-language", default="ur", choices=["ur", "en"])
        parser.add_argument("--save-speech", help="Write the synthesised audio to this file to listen to it.")
        parser.add_argument("--cnic-image", action="append", default=[], help="Synthetic card image for the OCR step (repeatable).")

    def report(self, step: str, ok: bool, detail: str) -> None:
        style = self.style.SUCCESS if ok else self.style.ERROR
        self.stdout.write(style(f"[{'OK' if ok else 'FAIL'}] {step}: {detail}"))

    def handle(self, *args, audio=None, language="ur", only=None, speak=SPEECH_SAMPLE, speak_language="ur",
               save_speech=None, cnic_image=(), **options):
        steps = (only,) if only else STEPS
        if len(speak) > settings.VOICE_LIMITS["MAX_SYNTHESIS_CHARS"]:
            raise CommandError(f"--speak is longer than {settings.VOICE_LIMITS['MAX_SYNTHESIS_CHARS']} characters.")
        text = SAMPLE_TEXT

        if "speech_to_text" in steps:
            text = self.check_speech_to_text(audio, language) or text
        if "interpretation" in steps:
            self.check_interpretation(text)
        if "text_to_speech" in steps:
            self.check_text_to_speech(speak, speak_language, save_speech)
        if "cnic_ocr" in steps:
            self.check_cnic_ocr(cnic_image)
        if "agreement_check" in steps:
            self.check_agreement()
        if "quote_terms" in steps:
            self.check_quote_terms(audio, language)

    def check_agreement(self) -> None:
        import time

        try:
            checker = registry.agreement_checker()
        except ProviderError as exc:
            self.report("agreement_check", False, f"{settings.AGREEMENT_CHECK_PROVIDER}: {exc.code} ({exc.reason})")
            return
        for label, sample, expected in AGREEMENT_SCENARIOS:
            if checker.simulated and "timing_mismatch" in expected:
                self.stdout.write(f"[SKIP] agreement_check[{label}]: the simulated checker covers materials only "
                                  "(in the app, a quote outside the requested time is flagged by the time rule).")
                continue
            started = time.monotonic()
            try:
                for attempt in range(4):
                    try:
                        result = checker.check(**sample)
                        break
                    except ProviderLimitReached as exc:
                        # Free-tier limits (tokens per minute) hit back-to-back scenarios: wait as the provider asks
                        # (15–60 s) and try again, up to 3 times. The app itself shows "could not run" with a retry.
                        if attempt == 3:
                            raise
                        wait = min(max(exc.retry_after_seconds or 20, 15), 60)
                        self.stdout.write(f"[WAIT] agreement_check[{label}]: {exc.reason}; retrying in {wait}s")
                        time.sleep(wait)
                        started = time.monotonic()
            except ProviderError as exc:
                self.report(f"agreement_check[{label}]", False, f"{checker.name}: {exc.code} ({exc.reason})")
                continue
            codes = [finding["code"] for finding in result.findings]
            self.report(
                f"agreement_check[{label}]", sorted(codes) == sorted(expected),
                f"{result.provider}/{result.model} simulated={result.simulated} findings={codes} expected={expected} "
                f"{time.monotonic() - started:.1f}s",
            )
            for finding in result.findings:
                self.stdout.write(f"    - {finding['code']} ask={finding['ask']} question={finding['question'][:160]!r}")
                for source in finding["sources"]:
                    self.stdout.write(f"        source {source['kind']}/{source['ref']}: {source['text'][:120]!r}")

    def check_cnic_ocr(self, images) -> None:
        import time

        from apps.workers.identity import inspect_image, mask_cnic

        if not images:
            self.stdout.write("[SKIP] cnic_ocr: pass --cnic-image <file> (e.g. docs/demo/cnic/*.png) to test OCR.")
            return
        for image in images:
            path = Path(image)
            if not path.is_file():
                raise CommandError(f"No such file: {path}")
            data = path.read_bytes()
            started = time.monotonic()
            try:
                mime_type, width, height = inspect_image(data)
                provider = registry.cnic_ocr()
                result = provider.extract(image=data, mime_type=mime_type)
            except ProviderError as exc:
                self.report("cnic_ocr", False, f"{path.name}: {settings.CNIC_OCR_PROVIDER}: {exc.code} ({exc.reason})")
                continue
            except Exception as exc:  # noqa: BLE001 — image validation errors carry a code
                self.report("cnic_ocr", False, f"{path.name}: {getattr(exc, 'default_code', type(exc).__name__)}")
                continue
            number = mask_cnic(result.cnic_number) if result.cnic_number else None
            self.report(
                "cnic_ocr", result.status != "unreadable",
                f"{path.name}: {result.provider} [{result.engine}] {width}x{height} status={result.status} "
                f"name={result.name!r} number={number} rotation={result.rotation} {time.monotonic() - started:.1f}s",
            )

    def check_speech_to_text(self, audio: str | None, language: str) -> str | None:
        if not audio:
            self.stdout.write("[SKIP] speech_to_text: pass --audio <file> to test transcription.")
            return None
        path = Path(audio)
        if not path.is_file():
            raise CommandError(f"No such file: {path}")
        data = path.read_bytes()
        info = inspect_audio(data)
        try:
            provider = registry.speech_to_text()
            result = provider.transcribe(
                audio=data, mime_type=info.format.provider_mime_type, language_hint=language,
                purpose="worker_introduction",
            )
        except ProviderError as exc:
            self.report("speech_to_text", False, f"{settings.SPEECH_TO_TEXT_PROVIDER}: {exc.code} ({exc.reason})")
            return None
        self.report(
            "speech_to_text",
            True,
            f"{result.provider}/{result.model} simulated={result.simulated} language={result.language} "
            f"no_speech={result.no_speech} transcript={result.text[:160]!r}",
        )
        return result.text

    def check_interpretation(self, text: str) -> None:
        import time

        samples = [
            ("worker_introduction", text, "mixed", None),
            ("job_description", JOB_SAMPLE_EN, "en",
             lambda f: f["trade"] == "electrician" and "elec_fan_install" in f["services"] and f["area"] == "isb-g-9"
             and "ac_service_cleaning" not in f["services"] and _urdu(f["description"])),
            ("onboarding_work", WORK_SAMPLE_UR, "mixed",
             lambda f: f["trade"] == "electrician" and "elec_fan_install" in f["services_offered"]
             and "elec_ups_inverter" not in f["services_offered"]),
            ("onboarding_areas", AREAS_SAMPLE_UR, "mixed",
             lambda f: f["city"] == "islamabad" and {"isb-g-9", "isb-g-10"} <= set(f["service_areas"])
             and "isb-f-8" not in f["service_areas"]),
        ]
        catalog = drafts.CatalogIndex.load()
        for kind, sample, language, expectation in samples:
            started = time.monotonic()
            try:
                provider = registry.interpretation()
                result = provider.interpret(kind=kind, text=sample, language=language, catalog=drafts.catalog_context(kind))
                draft = drafts.build_draft(kind, drafts.validate_raw(kind, result.raw), sample, catalog)
            except ProviderError as exc:
                self.report(f"interpretation[{kind}]", False, f"{settings.INTERPRETATION_PROVIDER}: {exc.code} ({exc.reason})")
                continue
            ok = expectation(draft["fields"]) if expectation else True
            self.report(
                f"interpretation[{kind}]", ok,
                f"{result.provider}/{result.model} simulated={result.simulated} fields={draft['fields']} "
                f"unmatched={draft['unmatched_mentions']} uncertain={draft['uncertain']} {time.monotonic() - started:.1f}s",
            )

    def _quote_expected(self, fields: dict) -> bool:
        today = drafts.karachi_today()
        ahead = (4 - today.weekday()) % 7  # Friday
        friday = None if ahead == 0 else (today + timedelta(days=ahead)).isoformat()  # said on a Friday: left unclear
        return (fields["labour_amount"] == 1200 and fields["materials"] == "customer" and fields["date"] == friday
                and (fields["start_time"], fields["end_time"]) == ("16:00", "18:00")
                and fields["labour_basis"] is None and fields["quantity"] is None and fields["materials_amount"] is None)

    def _interpret_quote(self, step: str, text: str, language: str) -> None:
        import time

        started = time.monotonic()
        try:
            result = registry.interpretation().interpret(kind="quote_terms", text=text, language=language,
                                                         catalog=drafts.catalog_context("quote_terms"))
            draft = drafts.build_draft("quote_terms", drafts.validate_raw("quote_terms", result.raw), text, drafts.CatalogIndex.load())
        except ProviderError as exc:
            self.report(step, False, f"{settings.INTERPRETATION_PROVIDER}: {exc.code} ({exc.reason})")
            return
        self.report(step, self._quote_expected(draft["fields"]),
                    f"{result.provider}/{result.model} simulated={result.simulated} fields={draft['fields']} "
                    f"missing={draft['missing']} uncertain={draft['uncertain']} heard={draft['heard']} "
                    f"{time.monotonic() - started:.1f}s")

    def check_quote_terms(self, audio: str | None, language: str) -> None:
        """Interpretation of the Urdu sample, then (live providers) speech → transcript → interpretation."""
        self._interpret_quote("quote_terms[text]", QUOTE_SAMPLE_UR, "ur")
        try:
            if audio:
                data = Path(audio).read_bytes()
            elif registry.text_to_speech().simulated or registry.speech_to_text().simulated:
                self.stdout.write("[SKIP] quote_terms[speech]: needs live text-to-speech and speech-to-text (or --audio).")
                return
            else:
                data = registry.text_to_speech().synthesize(text=QUOTE_SAMPLE_UR, language="ur").audio
        except ProviderError as exc:  # e.g. a provider selected without its key: reported, never raised
            self.report("quote_terms[speech]", False, f"{exc.code} ({exc.reason})")
            return
        info = inspect_audio(data)
        try:
            transcript = registry.speech_to_text().transcribe(audio=data, mime_type=info.format.provider_mime_type,
                                                            language_hint="ur" if language == "auto" else language,
                                                            purpose="quote_terms")
        except ProviderError as exc:
            self.report("quote_terms[transcript]", False, f"{settings.SPEECH_TO_TEXT_PROVIDER}: {exc.code} ({exc.reason})")
            return
        self.report("quote_terms[transcript]", bool(transcript.text.strip()),
                    f"{transcript.provider}/{transcript.model} language={transcript.language} text={transcript.text[:200]!r}")
        self._interpret_quote("quote_terms[speech]", transcript.text, transcript.language)

    def check_text_to_speech(self, text: str, language: str, save_to: str | None) -> None:
        try:
            provider = registry.text_to_speech()
            result = provider.synthesize(text=text, language=language)
        except ProviderError as exc:
            self.report("text_to_speech", False, f"{settings.TEXT_TO_SPEECH_PROVIDER}: {exc.code} ({exc.reason})")
            return
        detail = (
            f"{result.provider} voice={result.voice} simulated={result.simulated} "
            f"format={result.mime_type} bytes={len(result.audio)} text={text[:80]!r}"
        )
        if save_to:
            target = Path(save_to)
            expected = AUDIO_EXTENSIONS.get(result.mime_type)
            if expected and target.suffix.lower() != expected:
                target = target.with_suffix(expected)
            target.write_bytes(result.audio)
            detail += f" saved={target}"
        self.report("text_to_speech", True, detail)

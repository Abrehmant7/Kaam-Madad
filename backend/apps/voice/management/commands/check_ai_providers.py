"""Exercise each configured AI/audio provider once (live check). Prints no keys.

    python manage.py check_ai_providers --audio path/to/sample.wav [--language ur]
    python manage.py check_ai_providers --only text_to_speech --save-speech speech.mp3
    python manage.py check_ai_providers --only cnic_ocr --cnic-image ../docs/demo/cnic/demo-card-bilal-ahmed.png
    python manage.py check_ai_providers --only agreement_check

- Speech-to-text runs only with --audio (any supported format, ≤ 60 s, ≤ 10 MB).
- Interpretation uses the transcript (or a built-in fictional Urdu sample).
- Text-to-speech reads --speak (default: a fictional Urdu sentence with English trade terms),
  checks that real audio came back, and with --save-speech writes it to a file to listen to.
- CNIC OCR runs the configured OCR provider (Tesseract on this host) on each --cnic-image and prints
  the extracted name and the MASKED number. Use the synthetic DEMO cards in docs/demo/cnic/.
- Agreement check runs the configured checker on a built-in fictional request, two messages and a
  quote that disagree about materials (labour-only quote, request says materials included), and prints
  the findings with their verified source statements. A correct checker reports materials_responsibility.
Each step reports OK, or the error code and reason (not configured / limit / unavailable / invalid output).
Use fictional speech and text only — never real CNIC numbers or personal details.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.providers import registry
from apps.providers.errors import ProviderError
from apps.providers.text_to_speech import AUDIO_EXTENSIONS
from apps.voice import drafts
from apps.voice.audio import inspect_audio

SAMPLE_TEXT = "میرا نام احمد ہے۔ میں الیکٹریشن ہوں۔ میں پنکھے لگاتا ہوں لیکن motor rewinding نہیں کرتا۔"
SPEECH_SAMPLE = "احمد صاحب کل شام G-9 میں دو پنکھے لگائیں گے۔ AC کی service نہیں ہو گی۔"
STEPS = ("speech_to_text", "interpretation", "text_to_speech", "cnic_ocr", "agreement_check")
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

    def check_agreement(self) -> None:
        import time

        started = time.monotonic()
        try:
            result = registry.agreement_checker().check(**AGREEMENT_SAMPLE)
        except ProviderError as exc:
            self.report("agreement_check", False, f"{settings.AGREEMENT_CHECK_PROVIDER}: {exc.code} ({exc.reason})")
            return
        codes = [finding["code"] for finding in result.findings]
        self.report(
            "agreement_check", "materials_responsibility" in codes,
            f"{result.provider}/{result.model} simulated={result.simulated} findings={codes} {time.monotonic() - started:.1f}s",
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
        try:
            provider = registry.interpretation()
            result = provider.interpret(
                kind="worker_introduction", text=text, language="mixed",
                catalog=drafts.catalog_context("worker_introduction"),
            )
            draft = drafts.build_draft(
                "worker_introduction", drafts.validate_raw("worker_introduction", result.raw), text,
                drafts.CatalogIndex.load(),
            )
        except ProviderError as exc:
            self.report("interpretation", False, f"{settings.INTERPRETATION_PROVIDER}: {exc.code} ({exc.reason})")
            return
        self.report(
            "interpretation",
            True,
            f"{result.provider}/{result.model} simulated={result.simulated} fields={draft['fields']} "
            f"unmatched={draft['unmatched_mentions']} missing={draft['missing']}",
        )

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

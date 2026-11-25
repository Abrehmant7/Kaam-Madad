"""Exercise each configured AI/audio provider once (live check). Prints no keys.

    python manage.py check_ai_providers --audio path/to/sample.wav [--language ur]
    python manage.py check_ai_providers --only text_to_speech --save-speech speech.mp3

- Speech-to-text runs only with --audio (any supported format, ≤ 60 s, ≤ 10 MB).
- Interpretation uses the transcript (or a built-in fictional Urdu sample).
- Text-to-speech reads --speak (default: a fictional Urdu sentence with English trade terms),
  checks that real audio came back, and with --save-speech writes it to a file to listen to.
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
STEPS = ("speech_to_text", "interpretation", "text_to_speech")


class Command(BaseCommand):
    help = "Call each configured speech-to-text, interpretation and text-to-speech provider once."

    def add_arguments(self, parser):
        parser.add_argument("--audio", help="Path to a short fictional voice sample to transcribe.")
        parser.add_argument("--language", default="ur", choices=["ur", "en", "auto"])
        parser.add_argument("--only", choices=STEPS, help="Run just one step.")
        parser.add_argument("--speak", default=SPEECH_SAMPLE, help="Fictional text to read aloud.")
        parser.add_argument("--speak-language", default="ur", choices=["ur", "en"])
        parser.add_argument("--save-speech", help="Write the synthesised audio to this file to listen to it.")

    def report(self, step: str, ok: bool, detail: str) -> None:
        style = self.style.SUCCESS if ok else self.style.ERROR
        self.stdout.write(style(f"[{'OK' if ok else 'FAIL'}] {step}: {detail}"))

    def handle(self, *args, audio=None, language="ur", only=None, speak=SPEECH_SAMPLE, speak_language="ur",
               save_speech=None, **options):
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

"""Select the configured provider for each capability (AI-01).

Fixture (simulated) providers are only returned in a demo deployment. In live mode a
"fixture" setting is refused at startup (config.env.check_simulation_allowed) and, as
defence in depth, treated as not configured here — fixture results are never returned live.
"""

from __future__ import annotations

from django.conf import settings

from config.env import DEPLOYMENT_MODE_DEMO

from .agreement import AgreementChecker, FixtureAgreementChecker, GeminiAgreementChecker, UnconfiguredAgreementChecker
from .errors import ProviderNotConfigured
from .identity import CnicOcrProvider, TesseractCnicOcr, UnconfiguredCnicOcr
from .interpretation import FixtureInterpretation, GeminiInterpretation, InterpretationProvider, UnconfiguredInterpretation
from .speech_to_text import FixtureSpeechToText, GeminiSpeechToText, SpeechToTextProvider, UnconfiguredSpeechToText
from .text_to_speech import (
    AzureTextToSpeech,
    ElevenLabsTextToSpeech,
    FixtureTextToSpeech,
    TextToSpeechProvider,
    UnconfiguredTextToSpeech,
)

FIXTURE = "fixture"


def _fixture_allowed() -> bool:
    return settings.DEPLOYMENT_MODE == DEPLOYMENT_MODE_DEMO


def speech_to_text() -> SpeechToTextProvider:
    choice = settings.SPEECH_TO_TEXT_PROVIDER
    if choice == FIXTURE:
        return FixtureSpeechToText() if _fixture_allowed() else UnconfiguredSpeechToText()
    if choice == "gemini":
        return GeminiSpeechToText()
    return UnconfiguredSpeechToText()


def interpretation() -> InterpretationProvider:
    choice = settings.INTERPRETATION_PROVIDER
    if choice == FIXTURE:
        return FixtureInterpretation() if _fixture_allowed() else UnconfiguredInterpretation()
    if choice == "gemini":
        return GeminiInterpretation()
    return UnconfiguredInterpretation()


def text_to_speech() -> TextToSpeechProvider:
    choice = settings.TEXT_TO_SPEECH_PROVIDER
    if choice == FIXTURE:
        return FixtureTextToSpeech() if _fixture_allowed() else UnconfiguredTextToSpeech()
    if choice == "azure":
        return AzureTextToSpeech()
    if choice == "elevenlabs":
        return ElevenLabsTextToSpeech()
    return UnconfiguredTextToSpeech()


def agreement_checker() -> AgreementChecker:
    choice = settings.AGREEMENT_CHECK_PROVIDER
    if choice == FIXTURE:
        return FixtureAgreementChecker() if _fixture_allowed() else UnconfiguredAgreementChecker()
    if choice == "gemini":
        return GeminiAgreementChecker()
    return UnconfiguredAgreementChecker()


def cnic_ocr() -> CnicOcrProvider:
    # Real local OCR only: there is no simulated OCR option (M4).
    if settings.CNIC_OCR_PROVIDER == "tesseract":
        return TesseractCnicOcr()
    return UnconfiguredCnicOcr()


def _status(choice: str, factory) -> dict:
    try:
        provider = factory()
    except ProviderNotConfigured:
        return {"provider": choice, "available": False, "simulated": False}
    available = provider.name != "unconfigured"
    return {"provider": provider.name, "available": available, "simulated": bool(provider.simulated)}


def status() -> dict:
    """Non-secret availability summary for GET /config/ (no keys, no models with secrets)."""
    return {
        "speech_to_text": _status(settings.SPEECH_TO_TEXT_PROVIDER, speech_to_text),
        "interpretation": _status(settings.INTERPRETATION_PROVIDER, interpretation),
        "text_to_speech": _status(settings.TEXT_TO_SPEECH_PROVIDER, text_to_speech),
        "cnic_ocr": _status(settings.CNIC_OCR_PROVIDER, cnic_ocr),
        "agreement_check": _status(settings.AGREEMENT_CHECK_PROVIDER, agreement_checker),
    }

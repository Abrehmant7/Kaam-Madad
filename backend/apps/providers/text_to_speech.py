"""Text-to-speech adapters (AI-01, UX-03, MSG-02).

Selected by settings.TEXT_TO_SPEECH_PROVIDER:
- "azure": Azure AI Speech neural TTS REST API. Urdu uses an ur-PK neural voice
  (default ur-PK-UzmaNeural), English an en-IN voice (default en-IN-NeerjaNeural).
  Endpoint https://{region}.tts.speech.microsoft.com/cognitiveservices/v1 with
  Ocp-Apim-Subscription-Key, Content-Type application/ssml+xml,
  X-Microsoft-OutputFormat riff-24khz-16bit-mono-pcm (WAV, plays in every browser).
  The Gemini API's TTS language list does not include Urdu, so Gemini is not used here.
- "elevenlabs": ElevenLabs text-to-speech REST API with model eleven_v3 (lists Urdu "ur"
  among its 70+ languages; Multilingual v2 and Flash v2.5 do not). One configured voice
  (ELEVENLABS_VOICE_ID) reads both Urdu and English; language_code is sent as a hint.
  POST {base}/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128 with header
  xi-api-key. MP3 (default) or WAV output formats only, checked by magic bytes.
- "fixture": a short generated tone (NOT speech), labelled simulated; demo/test only.
- "unconfigured": always ProviderNotConfigured.
"""

from __future__ import annotations

import io
import math
import re
import struct
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import quote, urlencode
from xml.sax.saxutils import escape, quoteattr

import httpx
from django.conf import settings

from . import http
from .errors import ProviderError, ProviderInvalidOutput, ProviderLimitReached, ProviderNotConfigured, ProviderUnavailable

LANGUAGES = ("ur", "en")
# File extension for each audio type a provider may return (used for private storage names).
AUDIO_EXTENSIONS = {"audio/wav": ".wav", "audio/mpeg": ".mp3"}


def looks_like_wav(audio: bytes) -> bool:
    return len(audio) >= 44 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"


def looks_like_mp3(audio: bytes) -> bool:
    if len(audio) < 4:
        return False
    return audio[:3] == b"ID3" or (audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0)


@dataclass(frozen=True)
class SpeechResult:
    audio: bytes
    mime_type: str
    voice: str
    provider: str
    simulated: bool


class TextToSpeechProvider(ABC):
    name: str
    simulated: bool = False

    @abstractmethod
    def voice_for(self, language: str) -> str: ...

    @abstractmethod
    def synthesize(self, *, text: str, language: str) -> SpeechResult: ...


class FixtureTextToSpeech(TextToSpeechProvider):
    """Generates a soft two-tone WAV whose length grows with the text (max 3 s). Not speech."""

    name = "fixture"
    simulated = True

    def voice_for(self, language: str) -> str:
        return f"fixture-tone-{language}"

    def synthesize(self, *, text: str, language: str) -> SpeechResult:
        rate = 16000
        seconds = min(0.6 + len(text) / 120, 3.0)
        frequency = 440.0 if language == "ur" else 523.25
        frames = bytearray()
        for i in range(int(rate * seconds)):
            t = i / rate
            envelope = min(1.0, t * 8, (seconds - t) * 8)
            value = 0.2 * envelope * math.sin(2 * math.pi * frequency * t)
            frames += struct.pack("<h", int(value * 32767))
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(bytes(frames))
        return SpeechResult(audio=buffer.getvalue(), mime_type="audio/wav", voice=self.voice_for(language), provider=self.name, simulated=True)


class AzureTextToSpeech(TextToSpeechProvider):
    name = "azure"

    def __init__(self, client: httpx.Client | None = None):
        if not settings.AZURE_SPEECH_KEY or not settings.AZURE_SPEECH_REGION:
            raise ProviderNotConfigured("missing_api_key")
        self.client = client or http.default_client()
        self.url = f"https://{settings.AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"

    def voice_for(self, language: str) -> str:
        return settings.AZURE_TTS_VOICE_UR if language == "ur" else settings.AZURE_TTS_VOICE_EN

    def synthesize(self, *, text: str, language: str) -> SpeechResult:
        voice = self.voice_for(language)
        locale = "-".join(voice.split("-")[:2])  # e.g. "ur-PK" from "ur-PK-UzmaNeural"
        ssml = (
            f"<speak version='1.0' xml:lang={quoteattr(locale)}>"
            f"<voice xml:lang={quoteattr(locale)} name={quoteattr(voice)}>{escape(text)}</voice></speak>"
        )
        response = http.post(
            self.client,
            self.url,
            provider=self.name,
            headers={
                "Ocp-Apim-Subscription-Key": settings.AZURE_SPEECH_KEY,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": settings.AZURE_TTS_OUTPUT_FORMAT,
                "User-Agent": "kaam-madad",
            },
            content=ssml.encode("utf-8"),
        )
        audio = response.content
        if len(audio) < 44 or audio[:4] != b"RIFF":
            raise ProviderInvalidOutput("audio_not_wav")
        return SpeechResult(audio=audio, mime_type="audio/wav", voice=voice, provider=self.name, simulated=False)


_ELEVENLABS_VOICE_ID = re.compile(r"^[A-Za-z0-9]{1,40}$")
_ELEVENLABS_MODEL_ID = re.compile(r"^[a-z0-9_]{1,40}$")
_ELEVENLABS_FORMAT = re.compile(r"^(mp3|wav)_\d{4,5}(_\d{2,3})?$")
# Documented ElevenLabs error codes (``{"detail": {"status": <code>, ...}}``) mapped to our taxonomy.
# Unknown codes fall back to the HTTP-status mapping in http.post. Provider text is never echoed.
_ELEVENLABS_ERRORS = {
    "quota_exceeded": ProviderLimitReached,
    "too_many_concurrent_requests": ProviderLimitReached,
    "system_busy": ProviderUnavailable,
    "invalid_api_key": ProviderNotConfigured,
    "voice_not_found": ProviderNotConfigured,
}


def _elevenlabs_error(response: httpx.Response) -> ProviderError | None:
    try:
        body = response.json()
    except ValueError:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    if not isinstance(detail, dict):
        return None
    # Check both fields: e.g. {"code": "invalid_api_key", "status": "api_key_id_used_as_api_key"}.
    for code in (detail.get("status"), detail.get("code")):
        error_class = _ELEVENLABS_ERRORS.get(code) if isinstance(code, str) else None
        if error_class is not None:
            reason = "credentials_rejected" if code == "invalid_api_key" else code
            return error_class(reason, retry_after_seconds=http.retry_after(response))
    if detail.get("type") == "authentication_error":
        return ProviderNotConfigured("credentials_rejected")
    return None


class ElevenLabsTextToSpeech(TextToSpeechProvider):
    name = "elevenlabs"

    def __init__(self, client: httpx.Client | None = None):
        if not settings.ELEVENLABS_API_KEY:
            raise ProviderNotConfigured("missing_api_key")
        if not settings.ELEVENLABS_VOICE_ID:
            raise ProviderNotConfigured("missing_voice_id")
        if not _ELEVENLABS_VOICE_ID.match(settings.ELEVENLABS_VOICE_ID):
            raise ProviderNotConfigured("invalid_voice_id")
        if not _ELEVENLABS_MODEL_ID.match(settings.ELEVENLABS_MODEL_ID):
            raise ProviderNotConfigured("invalid_model_id")
        output_format = settings.ELEVENLABS_OUTPUT_FORMAT
        if not _ELEVENLABS_FORMAT.match(output_format):
            raise ProviderNotConfigured("unsupported_output_format")
        self.mime_type = "audio/mpeg" if output_format.startswith("mp3_") else "audio/wav"
        query = {"output_format": output_format}
        if settings.ELEVENLABS_ZERO_RETENTION:
            query["enable_logging"] = "false"  # zero-retention mode (ElevenLabs enterprise accounts only)
        base = settings.ELEVENLABS_API_BASE.rstrip("/")
        self.url = f"{base}/v1/text-to-speech/{quote(settings.ELEVENLABS_VOICE_ID, safe='')}?{urlencode(query)}"
        self.client = client or http.default_client()

    def voice_for(self, language: str) -> str:
        # Model and voice together identify the sound, so changing either is not served from the reuse cache.
        return f"{settings.ELEVENLABS_MODEL_ID}/{settings.ELEVENLABS_VOICE_ID}"

    def synthesize(self, *, text: str, language: str) -> SpeechResult:
        response = http.post(
            self.client,
            self.url,
            provider=self.name,
            headers={"xi-api-key": settings.ELEVENLABS_API_KEY, "Accept": self.mime_type, "User-Agent": "kaam-madad"},
            json={"text": text, "model_id": settings.ELEVENLABS_MODEL_ID, "language_code": language},
            classify_error=_elevenlabs_error,
        )
        audio = response.content
        if self.mime_type == "audio/mpeg" and not looks_like_mp3(audio):
            raise ProviderInvalidOutput("audio_not_mp3")
        if self.mime_type == "audio/wav" and not looks_like_wav(audio):
            raise ProviderInvalidOutput("audio_not_wav")
        return SpeechResult(
            audio=audio, mime_type=self.mime_type, voice=self.voice_for(language), provider=self.name, simulated=False
        )


class UnconfiguredTextToSpeech(TextToSpeechProvider):
    name = "unconfigured"

    def voice_for(self, language: str) -> str:
        return ""

    def synthesize(self, **kwargs) -> SpeechResult:
        raise ProviderNotConfigured("no_provider_selected")

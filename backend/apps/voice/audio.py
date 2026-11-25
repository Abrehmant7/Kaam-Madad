"""Server-side audio validation (JOB-04, AI-03, SEC-01).

Runs BEFORE any audio is stored or sent to a provider:
1. Size ≤ VOICE_LIMITS["MAX_AUDIO_BYTES"] (10 MB).
2. Format detected from the file's bytes (magic numbers) — the client's declared
   content type and file name are ignored.
3. The file must parse as that format (mutagen) and report a duration between
   MIN_AUDIO_SECONDS and MAX_AUDIO_SECONDS (60 s, +0.25 s rounding tolerance).

Supported: WAV (what the in-app recorder produces), MP3, M4A/MP4 (AAC), AAC (ADTS),
OGG (Opus — e.g. WhatsApp voice notes — or Vorbis), FLAC. WebM is rejected because
its duration cannot be verified without extra tooling (the in-app recorder makes WAV).
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from django.conf import settings
from mutagen import MutagenError
from mutagen.aac import AAC
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE
from rest_framework import status

from apps.core.api.exceptions import ApiError

SUPPORTED_FORMATS_TEXT = "WAV, MP3, M4A (AAC), AAC, OGG (Opus/Vorbis), FLAC"
DURATION_TOLERANCE_SECONDS = 0.25


@dataclass(frozen=True)
class AudioFormat:
    kind: str
    mime_type: str  # served back to the owner
    provider_mime_type: str  # sent to the speech-to-text provider
    extension: str


FORMATS = {
    "wav": AudioFormat("wav", "audio/wav", "audio/wav", ".wav"),
    "mp3": AudioFormat("mp3", "audio/mpeg", "audio/mp3", ".mp3"),
    "m4a": AudioFormat("m4a", "audio/mp4", "audio/m4a", ".m4a"),
    "aac": AudioFormat("aac", "audio/aac", "audio/aac", ".aac"),
    "ogg": AudioFormat("ogg", "audio/ogg", "audio/ogg", ".ogg"),
    "flac": AudioFormat("flac", "audio/flac", "audio/flac", ".flac"),
}


class AudioTooLarge(ApiError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_code = "audio_too_large"
    default_detail = "The audio file is larger than 10 MB."


class AudioUnsupported(ApiError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_code = "audio_unsupported"
    default_detail = f"Unsupported audio format. Supported: {SUPPORTED_FORMATS_TEXT}."


class AudioInvalid(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "audio_invalid"
    default_detail = "The audio file could not be read."


class AudioTooLong(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "audio_too_long"
    default_detail = "The recording is longer than 60 seconds."


class AudioTooShort(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "audio_too_short"
    default_detail = "The recording is too short."


@dataclass(frozen=True)
class AudioInfo:
    format: AudioFormat
    duration_seconds: float
    size_bytes: int
    sha256: str


def sniff_format(head: bytes) -> str | None:
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"OggS":
        return "ogg"
    if head[4:8] == b"ftyp":
        return "m4a"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if head[:3] == b"ID3":
        return "mp3"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "aac" if ((head[1] >> 1) & 0x03) == 0 else "mp3"
    return None


def _duration(kind: str, data: bytes) -> float:
    buffer = io.BytesIO(data)
    if kind == "wav":
        return float(WAVE(buffer).info.length)
    if kind == "flac":
        return float(FLAC(buffer).info.length)
    if kind == "mp3":
        info = MP3(buffer).info
        if getattr(info, "sketchy", False):
            raise AudioInvalid()
        return float(info.length)
    if kind == "aac":
        return float(AAC(buffer).info.length)
    if kind == "m4a":
        info = MP4(buffer).info
        if not str(getattr(info, "codec", "")).startswith(("mp4a", "alac")):
            raise AudioUnsupported()  # e.g. a video track or another codec
        return float(info.length)
    if kind == "ogg":
        for parser in (OggOpus, OggVorbis):
            try:
                return float(parser(io.BytesIO(data)).info.length)
            except MutagenError:
                continue
        raise AudioUnsupported()
    raise AudioUnsupported()


def inspect_audio(data: bytes) -> AudioInfo:
    limits = settings.VOICE_LIMITS
    if len(data) > limits["MAX_AUDIO_BYTES"]:
        raise AudioTooLarge(details={"max_bytes": limits["MAX_AUDIO_BYTES"]})
    if not data:
        raise AudioInvalid()
    kind = sniff_format(data[:16])
    if kind is None or kind not in FORMATS:
        raise AudioUnsupported(details={"supported": SUPPORTED_FORMATS_TEXT})
    try:
        duration = _duration(kind, data)
    except ApiError:
        raise
    except (MutagenError, ValueError, ZeroDivisionError, OverflowError):
        raise AudioInvalid() from None
    if duration < limits["MIN_AUDIO_SECONDS"]:
        raise AudioTooShort(details={"min_seconds": limits["MIN_AUDIO_SECONDS"]})
    if duration > limits["MAX_AUDIO_SECONDS"] + DURATION_TOLERANCE_SECONDS:
        raise AudioTooLong(details={"max_seconds": limits["MAX_AUDIO_SECONDS"], "duration_seconds": round(duration, 1)})
    return AudioInfo(
        format=FORMATS[kind],
        duration_seconds=round(duration, 2),
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )

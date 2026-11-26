"""Voice API: private audio upload/playback, transcription, interpretation drafts, synthesis.

All endpoints require a signed-in, active user and only ever touch that user's own
records (others get 404, so existence is not revealed). Raw audio, transcripts and
synthesized text are never logged. Contracts: docs/api.md.
"""

from __future__ import annotations

import hashlib
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import StrictFieldsMixin
from apps.accounts.throttles import ConfigurableRateThrottle
from apps.core.api.exceptions import ApiError
from apps.providers import registry
from apps.providers.errors import ProviderError
from apps.providers.speech_to_text import LANGUAGE_HINTS
from apps.providers.text_to_speech import AUDIO_EXTENSIONS, LANGUAGES as SYNTH_LANGUAGES

from . import drafts, services
from .audio import AudioTooLarge, inspect_audio
from .instructions import INSTRUCTIONS
from .models import AudioClip, InstructionAudio, Interpretation, Purpose, SpeechSynthesis, Transcription

PROVIDER_MESSAGES = {
    "ai_provider_not_configured": "This AI service is not configured on the server.",
    "ai_provider_limit_reached": "The AI service usage limit was reached. Please try again later.",
    "ai_provider_unavailable": "The AI service did not respond. Please try again.",
    "ai_output_invalid": "The AI service returned an unusable result. Please try again or type instead.",
}


def provider_api_error(exc: ProviderError, capability: str) -> ApiError:
    details = {"capability": capability, "reason": exc.reason}
    if exc.retry_after_seconds:
        details["retry_after_seconds"] = exc.retry_after_seconds
    return ApiError(PROVIDER_MESSAGES[exc.code], exc.code, details=details, status_code=exc.status_code)


class _PerUserThrottle(ConfigurableRateThrottle):
    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class AudioUploadThrottle(_PerUserThrottle):
    scope = "audio_upload_user"


class AiRequestThrottle(_PerUserThrottle):
    scope = "ai_request_user"


def _private_file_response(field_file, mime_type: str, filename: str) -> FileResponse:
    response = FileResponse(field_file.open("rb"), content_type=mime_type)
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


# --- Payloads -----------------------------------------------------------------------------


def clip_payload(clip: AudioClip) -> dict:
    return {
        "id": str(clip.id),
        "purpose": clip.purpose,
        "source": clip.source,
        "mime_type": clip.mime_type,
        "size_bytes": clip.size_bytes,
        "duration_seconds": float(clip.duration_seconds),
        "created_at": clip.created_at.isoformat(),
        "content_url": f"/api/v1/audio/clips/{clip.id}/content/",
    }


def transcription_payload(transcription: Transcription, reused: bool) -> dict:
    return {
        "id": str(transcription.id),
        "clip_id": str(transcription.clip_id),
        "text": transcription.text,
        "language": transcription.language,
        "language_hint": transcription.language_hint,
        "no_speech": transcription.no_speech,
        "provider": transcription.provider,
        "model": transcription.model,
        "simulated": transcription.simulated,
        "reused": reused,
        "created_at": transcription.created_at.isoformat(),
    }


def interpretation_payload(interpretation: Interpretation, reused: bool = False) -> dict:
    return {
        "id": str(interpretation.id),
        "kind": interpretation.kind,
        "language": interpretation.language,
        "source": {
            "text": interpretation.source_text,
            "transcription_id": str(interpretation.transcription_id) if interpretation.transcription_id else None,
        },
        "draft": interpretation.draft,
        "corrections": interpretation.corrections,
        "effective_fields": drafts.effective_fields(interpretation.draft, interpretation.corrections),
        "confirmed": (
            {"fields": interpretation.confirmed_fields, "confirmed_at": interpretation.confirmed_at.isoformat()}
            if interpretation.confirmed_at
            else None
        ),
        "provider": interpretation.provider,
        "model": interpretation.model,
        "simulated": interpretation.simulated,
        "reused": reused,
        "created_at": interpretation.created_at.isoformat(),
    }


def synthesis_payload(synthesis: SpeechSynthesis, reused: bool) -> dict:
    return {
        "id": str(synthesis.id),
        "language": synthesis.language,
        "voice": synthesis.voice,
        "provider": synthesis.provider,
        "simulated": synthesis.simulated,
        "mime_type": synthesis.mime_type,
        "size_bytes": synthesis.size_bytes,
        "content_url": f"/api/v1/audio/syntheses/{synthesis.id}/content/",
        "reused": reused,
    }


# --- Serializers -------------------------------------------------------------------------


class UploadSerializer(StrictFieldsMixin, serializers.Serializer):
    file = serializers.FileField()
    purpose = serializers.ChoiceField(choices=Purpose.choices)
    source = serializers.ChoiceField(choices=AudioClip.Source.choices, default=AudioClip.Source.UPLOAD)


class TranscribeSerializer(StrictFieldsMixin, serializers.Serializer):
    clip_id = serializers.UUIDField()
    language = serializers.ChoiceField(choices=LANGUAGE_HINTS, default="ur")


class InterpretSerializer(StrictFieldsMixin, serializers.Serializer):
    kind = serializers.ChoiceField(choices=Purpose.choices)
    language = serializers.ChoiceField(choices=["ur", "en", "mixed", "unknown"], default="ur")
    transcription_id = serializers.UUIDField(required=False)
    text = serializers.CharField(required=False, trim_whitespace=True)

    def validate(self, attrs):
        has_transcription, has_text = "transcription_id" in attrs, bool(attrs.get("text"))
        if has_transcription == has_text:
            raise serializers.ValidationError(
                "Send either transcription_id or text.", code="transcription_or_text_required"
            )
        if has_text and len(attrs["text"]) > settings.VOICE_LIMITS["MAX_INTERPRET_CHARS"]:
            raise serializers.ValidationError({"text": [serializers.ErrorDetail("Too long.", code="max_length")]})
        return attrs


class SynthesiseSerializer(StrictFieldsMixin, serializers.Serializer):
    text = serializers.CharField(trim_whitespace=True)
    language = serializers.ChoiceField(choices=SYNTH_LANGUAGES)

    def validate_text(self, value):
        if len(value) > settings.VOICE_LIMITS["MAX_SYNTHESIS_CHARS"]:
            raise serializers.ValidationError("Too long.", code="max_length")
        return value


# --- Views ----------------------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class AudioClipUploadView(APIView):
    """POST /api/v1/audio/clips/ (multipart: file, purpose, source)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]
    throttle_classes = [AudioUploadThrottle]

    def post(self, request):
        # Reject oversized bodies before parsing (multipart overhead allowance: 64 KB).
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
        if declared > settings.VOICE_LIMITS["MAX_AUDIO_BYTES"] + 64 * 1024:
            raise AudioTooLarge(details={"max_bytes": settings.VOICE_LIMITS["MAX_AUDIO_BYTES"]})
        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        if upload.size > settings.VOICE_LIMITS["MAX_AUDIO_BYTES"]:
            raise AudioTooLarge(details={"max_bytes": settings.VOICE_LIMITS["MAX_AUDIO_BYTES"]})
        data = upload.read()
        info = inspect_audio(data)  # format, content and duration checked before storage
        clip = AudioClip(
            owner=request.user,
            purpose=serializer.validated_data["purpose"],
            source=serializer.validated_data["source"],
            mime_type=info.format.mime_type,
            provider_mime_type=info.format.provider_mime_type,
            size_bytes=info.size_bytes,
            duration_seconds=info.duration_seconds,
            sha256=info.sha256,
        )
        clip.file.save(f"clip{info.format.extension}", ContentFile(data), save=True)
        return Response(clip_payload(clip), status=status.HTTP_201_CREATED)


@method_decorator(never_cache, name="dispatch")
class AudioClipDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, clip_id):
        clip = get_object_or_404(AudioClip, pk=clip_id, owner=request.user)
        return Response(clip_payload(clip))


class AudioClipContentView(APIView):
    """GET /api/v1/audio/clips/<id>/content/ — owner only, private, not cacheable."""

    permission_classes = [IsAuthenticated]

    def get(self, request, clip_id):
        clip = get_object_or_404(AudioClip, pk=clip_id, owner=request.user)
        extension = os.path.splitext(clip.file.name)[1]
        return _private_file_response(clip.file, clip.mime_type, f"recording{extension}")


@method_decorator(never_cache, name="dispatch")
class TranscribeView(APIView):
    """POST /api/v1/audio/transcribe/ {clip_id, language}."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AiRequestThrottle]

    def post(self, request):
        serializer = TranscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        clip = get_object_or_404(AudioClip, pk=serializer.validated_data["clip_id"], owner=request.user)
        try:
            transcription, reused = services.transcribe(clip, serializer.validated_data["language"])
        except ProviderError as exc:
            raise provider_api_error(exc, "speech_to_text") from None
        return Response(transcription_payload(transcription, reused))


@method_decorator(never_cache, name="dispatch")
class InterpretationCreateView(APIView):
    """POST /api/v1/interpretations/ {kind, language, transcription_id | text}."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AiRequestThrottle]

    def post(self, request):
        serializer = InterpretSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        transcription = None
        if "transcription_id" in data:
            transcription = get_object_or_404(Transcription, pk=data["transcription_id"], clip__owner=request.user)
            text = transcription.text
            if not text.strip():
                raise ApiError("The recording contained no speech.", "no_speech", status_code=400)
        else:
            text = data["text"]
        try:
            interpretation, reused = services.interpret(
                owner=request.user, kind=data["kind"], text=text, language=data["language"], transcription=transcription
            )
        except ProviderError as exc:
            raise provider_api_error(exc, "interpretation") from None
        return Response(interpretation_payload(interpretation, reused), status=status.HTTP_201_CREATED)


@method_decorator(never_cache, name="dispatch")
class InterpretationDetailView(APIView):
    """GET a draft; PATCH {"fields": {...}} to save corrections (stored separately from the draft)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def get(self, request, interpretation_id):
        interpretation = get_object_or_404(Interpretation, pk=interpretation_id, owner=request.user)
        return Response(interpretation_payload(interpretation))

    def patch(self, request, interpretation_id):
        interpretation = get_object_or_404(Interpretation, pk=interpretation_id, owner=request.user)
        if interpretation.confirmed_at:
            raise ApiError("This draft is already confirmed.", "draft_already_confirmed", status_code=409)
        cleaned = drafts.clean_corrections(interpretation.kind, request.data, drafts.CatalogIndex.load())
        interpretation.corrections = {**interpretation.corrections, **cleaned}
        interpretation.save(update_fields=["corrections", "updated_at"])
        return Response(interpretation_payload(interpretation))


@method_decorator(never_cache, name="dispatch")
class InterpretationConfirmView(APIView):
    """POST: confirm the corrected draft. Confirmation stores the draft only — it publishes nothing."""

    permission_classes = [IsAuthenticated]

    def post(self, request, interpretation_id):
        interpretation = get_object_or_404(Interpretation, pk=interpretation_id, owner=request.user)
        if interpretation.confirmed_at:
            raise ApiError("This draft is already confirmed.", "draft_already_confirmed", status_code=409)
        fields = drafts.effective_fields(interpretation.draft, interpretation.corrections)
        drafts.validate_for_confirmation(interpretation.kind, fields)
        interpretation.confirmed_fields = fields
        interpretation.confirmed_at = timezone.now()
        interpretation.save(update_fields=["confirmed_fields", "confirmed_at", "updated_at"])
        return Response(interpretation_payload(interpretation))


@method_decorator(never_cache, name="dispatch")
class SynthesiseView(APIView):
    """POST /api/v1/audio/synthesise/ {text, language} → playable private audio."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AiRequestThrottle]

    def post(self, request):
        serializer = SynthesiseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            synthesis, reused = services.synthesise(
                owner=request.user, text=serializer.validated_data["text"], language=serializer.validated_data["language"]
            )
        except ProviderError as exc:
            raise provider_api_error(exc, "text_to_speech") from None
        return Response(synthesis_payload(synthesis, reused), status=status.HTTP_201_CREATED)


class SynthesisContentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, synthesis_id):
        synthesis = get_object_or_404(SpeechSynthesis, pk=synthesis_id, owner=request.user)
        extension = AUDIO_EXTENSIONS.get(synthesis.mime_type, ".bin")
        return _private_file_response(synthesis.file, synthesis.mime_type, f"speech{extension}")


class InstructionAudioThrottle(ConfigurableRateThrottle):
    scope = "instruction_audio_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class InstructionAudioView(APIView):
    """GET /api/v1/instructions/{key}/audio/?language=ur — speech for a FIXED instruction.

    Public (the signup screen is before login). Only known keys; the text comes from the server.
    Header ``X-Audio-Simulated: 1`` marks the fixture tone (not speech).
    """

    authentication_classes: list = []
    permission_classes: list = []
    throttle_classes = [InstructionAudioThrottle]

    def get(self, request, key):
        language = request.query_params.get("language", "ur")
        texts = INSTRUCTIONS.get(key)
        if texts is None or language not in texts:
            raise ApiError("Unknown instruction.", "not_found", status_code=status.HTTP_404_NOT_FOUND)
        text = texts[language]
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        try:
            provider = registry.text_to_speech()
            voice = provider.voice_for(language)
            audio = InstructionAudio.objects.filter(
                key=key, language=language, text_hash=text_hash, provider=provider.name, voice=voice
            ).first()
            if audio is None:
                result = provider.synthesize(text=text, language=language)
                audio = InstructionAudio(
                    key=key, language=language, text_hash=text_hash, provider=result.provider, voice=result.voice,
                    simulated=result.simulated, mime_type=result.mime_type, size_bytes=len(result.audio),
                )
                audio.file.save(f"instruction{AUDIO_EXTENSIONS.get(result.mime_type, '.bin')}", ContentFile(result.audio), save=False)
                try:
                    with transaction.atomic():
                        audio.save()
                except IntegrityError:
                    audio.file.delete(save=False)
                    audio = InstructionAudio.objects.get(
                        key=key, language=language, text_hash=text_hash, provider=result.provider, voice=result.voice
                    )
        except ProviderError as exc:
            raise provider_api_error(exc, "text_to_speech") from None
        response = FileResponse(audio.file.open("rb"), content_type=audio.mime_type)
        response["Cache-Control"] = "private, max-age=3600"
        response["X-Audio-Simulated"] = "1" if audio.simulated else "0"
        return response

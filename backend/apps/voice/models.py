"""Private audio and AI-assisted drafts (M3; requirements §5, DATA-02, MEDIA-01).

- Files live in private storage (MEDIA_ROOT = PRIVATE_MEDIA_ROOT, never served by URL);
  downloads go through views that check ownership on every request.
- File names are random and contain no user identifiers.
- The original transcript/text is kept separately from the model draft, and the
  user's corrections are kept separately from both (DATA-02).
- Nothing here publishes a profile, creates a job, or performs a marketplace action.
"""

from __future__ import annotations

import os
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS_STORED = 60.5  # 60 s limit plus rounding tolerance


def _random_path(prefix: str, filename: str) -> str:
    extension = os.path.splitext(filename)[1].lower()[:8]
    return f"{prefix}/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{extension}"


def audio_upload_path(instance, filename: str) -> str:
    return _random_path("audio", filename)


def synthesis_upload_path(instance, filename: str) -> str:
    return _random_path("speech", filename)


class Purpose(models.TextChoices):
    WORKER_INTRODUCTION = "worker_introduction", "Worker introduction"
    JOB_DESCRIPTION = "job_description", "Job description"
    MESSAGE = "message", "Conversation voice note"


class AudioClip(models.Model):
    class Source(models.TextChoices):
        RECORDING = "recording", "Browser recording"
        UPLOAD = "upload", "File upload"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="audio_clips")
    purpose = models.CharField(max_length=32, choices=Purpose.choices)
    source = models.CharField(max_length=16, choices=Source.choices)
    file = models.FileField(upload_to=audio_upload_path, max_length=200)
    mime_type = models.CharField(max_length=32)
    provider_mime_type = models.CharField(max_length=32)
    size_bytes = models.PositiveIntegerField()
    duration_seconds = models.DecimalField(max_digits=5, decimal_places=2)
    sha256 = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(size_bytes__gt=0, size_bytes__lte=MAX_AUDIO_BYTES), name="voice_clip_size_limit"
            ),
            models.CheckConstraint(
                condition=Q(duration_seconds__gt=0, duration_seconds__lte=MAX_AUDIO_SECONDS_STORED),
                name="voice_clip_duration_limit",
            ),
        ]


class Transcription(models.Model):
    """Original transcript in the spoken language. Reused for identical clip + provider + model + hint."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clip = models.ForeignKey(AudioClip, on_delete=models.CASCADE, related_name="transcriptions")
    provider = models.CharField(max_length=32)
    model = models.CharField(max_length=64)
    language_hint = models.CharField(max_length=8)
    text = models.TextField(blank=True)
    language = models.CharField(max_length=8)
    no_speech = models.BooleanField(default=False)
    simulated = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["clip", "provider", "model", "language_hint"], name="voice_transcription_reuse_key"
            ),
        ]


class Interpretation(models.Model):
    """An editable AI draft. ``draft`` is the validated model output (immutable);
    ``corrections`` holds the user's edits; ``confirmed_fields`` the confirmed result."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="interpretations")
    kind = models.CharField(max_length=32, choices=Purpose.choices)
    language = models.CharField(max_length=8)
    source_text = models.TextField()
    transcription = models.ForeignKey(Transcription, null=True, blank=True, on_delete=models.SET_NULL)
    input_hash = models.CharField(max_length=64)
    provider = models.CharField(max_length=32)
    model = models.CharField(max_length=64)
    simulated = models.BooleanField(default=False)
    draft = models.JSONField()
    corrections = models.JSONField(default=dict, blank=True)
    confirmed_fields = models.JSONField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    reused_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "input_hash"], name="voice_interp_reuse_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(confirmed_at__isnull=True, confirmed_fields__isnull=True)
                | Q(confirmed_at__isnull=False, confirmed_fields__isnull=False),
                name="voice_interp_confirmation_consistent",
            ),
        ]


class SpeechSynthesis(models.Model):
    """Audio for confirmed text. Cached per owner only (never a shared public cache, MSG-02)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="speech_syntheses")
    language = models.CharField(max_length=8)
    text = models.TextField()
    text_hash = models.CharField(max_length=64)
    provider = models.CharField(max_length=32)
    voice = models.CharField(max_length=64)
    simulated = models.BooleanField(default=False)
    file = models.FileField(upload_to=synthesis_upload_path, max_length=200)
    mime_type = models.CharField(max_length=32)
    size_bytes = models.PositiveIntegerField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "text_hash", "language", "provider", "voice"], name="voice_synthesis_reuse_key"
            ),
        ]


def instruction_upload_path(instance, filename: str) -> str:
    return _random_path("instructions", filename)


class InstructionAudio(models.Model):
    """Cached speech for a FIXED instruction (apps.voice.instructions). Public content, no owner."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=64)
    language = models.CharField(max_length=8)
    text_hash = models.CharField(max_length=64)
    provider = models.CharField(max_length=32)
    voice = models.CharField(max_length=64)
    simulated = models.BooleanField(default=False)
    file = models.FileField(upload_to=instruction_upload_path, max_length=200)
    mime_type = models.CharField(max_length=32)
    size_bytes = models.PositiveIntegerField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["key", "language", "text_hash", "provider", "voice"], name="voice_instruction_audio_key"
            ),
        ]

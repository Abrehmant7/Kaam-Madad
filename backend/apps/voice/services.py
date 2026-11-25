"""Orchestration for transcription, interpretation and synthesis.

Unchanged input is never reprocessed (NFR-02): a completed transcription is reused
for the same clip/provider/model/hint, an interpretation draft for the same
owner/text/kind/provider/model/catalog, and synthesized audio for the same
owner/text/language/voice. Reuse is per owner — no shared cache of private audio.
"""

from __future__ import annotations

import hashlib
import logging

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction

from apps.providers import registry
from apps.providers.text_to_speech import AUDIO_EXTENSIONS

from . import drafts
from .models import AudioClip, Interpretation, SpeechSynthesis, Transcription

logger = logging.getLogger(__name__)


def transcribe(clip: AudioClip, language_hint: str) -> tuple[Transcription, bool]:
    provider = registry.speech_to_text()
    existing = Transcription.objects.filter(
        clip=clip, provider=provider.name, model=provider.model, language_hint=language_hint
    ).first()
    if existing:
        return existing, True
    with clip.file.open("rb") as handle:
        audio = handle.read()
    result = provider.transcribe(
        audio=audio, mime_type=clip.provider_mime_type, language_hint=language_hint, purpose=clip.purpose
    )
    try:
        with transaction.atomic():
            transcription = Transcription.objects.create(
                clip=clip,
                provider=result.provider,
                model=result.model,
                language_hint=language_hint,
                text=result.text,
                language=result.language,
                no_speech=result.no_speech,
                simulated=result.simulated,
            )
    except IntegrityError:  # a concurrent request finished first
        transcription = Transcription.objects.get(
            clip=clip, provider=result.provider, model=result.model, language_hint=language_hint
        )
        return transcription, True
    logger.info("Transcribed clip with %s (simulated=%s).", result.provider, result.simulated)
    return transcription, False


def interpret(
    *, owner, kind: str, text: str, language: str, transcription: Transcription | None = None
) -> tuple[Interpretation, bool]:
    provider = registry.interpretation()
    catalog = drafts.CatalogIndex.load()
    key = drafts.input_hash(kind, language, text, provider.name, provider.model, catalog)

    previous = (
        Interpretation.objects.filter(owner=owner, input_hash=key).order_by("-created_at").first()
    )
    if previous:
        # Reuse the provider result; the new record gets its own (empty) corrections.
        return (
            Interpretation.objects.create(
                owner=owner, kind=kind, language=language, source_text=text, transcription=transcription,
                input_hash=key, provider=previous.provider, model=previous.model, simulated=previous.simulated,
                draft=previous.draft, reused_from=previous,
            ),
            True,
        )

    result = provider.interpret(kind=kind, text=text, language=language, catalog=drafts.catalog_context(kind))
    raw = drafts.validate_raw(kind, result.raw)
    draft = drafts.build_draft(kind, raw, text, catalog)
    interpretation = Interpretation.objects.create(
        owner=owner, kind=kind, language=language, source_text=text, transcription=transcription,
        input_hash=key, provider=result.provider, model=result.model, simulated=result.simulated, draft=draft,
    )
    logger.info("Interpreted %s with %s (simulated=%s).", kind, result.provider, result.simulated)
    return interpretation, False


def synthesise(*, owner, text: str, language: str) -> tuple[SpeechSynthesis, bool]:
    provider = registry.text_to_speech()
    voice = provider.voice_for(language)
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    existing = SpeechSynthesis.objects.filter(
        owner=owner, text_hash=text_hash, language=language, provider=provider.name, voice=voice
    ).first()
    if existing:
        return existing, True
    result = provider.synthesize(text=text, language=language)
    synthesis = SpeechSynthesis(
        owner=owner, language=language, text=text, text_hash=text_hash, provider=result.provider,
        voice=result.voice, simulated=result.simulated, mime_type=result.mime_type, size_bytes=len(result.audio),
    )
    extension = AUDIO_EXTENSIONS.get(result.mime_type, ".bin")
    synthesis.file.save(f"speech{extension}", ContentFile(result.audio), save=False)
    try:
        with transaction.atomic():
            synthesis.save()
    except IntegrityError:
        synthesis.file.delete(save=False)
        return SpeechSynthesis.objects.get(
            owner=owner, text_hash=text_hash, language=language, provider=result.provider, voice=result.voice
        ), True
    return synthesis, False

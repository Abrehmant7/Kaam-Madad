"""Shared ElevenLabs conventions for the text-to-speech (eleven_v3) and speech-to-text (Scribe) adapters.

One server-side key (ELEVENLABS_API_KEY) serves both. An ElevenLabs key whose scope is restricted needs
*Text to Speech* access for read-aloud and *Speech to Text* access for transcription.
Errors: ElevenLabs reports its own codes as ``{"detail": {"status" | "code": <code>, ...}}``; they are
mapped to the shared taxonomy here. Unknown codes fall back to the HTTP-status mapping in ``http.post``.
Provider text is never echoed.
"""

from __future__ import annotations

import httpx

from . import http
from .errors import ProviderError, ProviderLimitReached, ProviderNotConfigured, ProviderUnavailable

PROVIDER = "elevenlabs"

_ERRORS = {
    "quota_exceeded": ProviderLimitReached,
    "too_many_concurrent_requests": ProviderLimitReached,
    "system_busy": ProviderUnavailable,
    "invalid_api_key": ProviderNotConfigured,
    "voice_not_found": ProviderNotConfigured,
    # 402: e.g. free plans cannot use Voice Library voices through the API — choose another voice or plan.
    "paid_plan_required": ProviderNotConfigured,
    # A key restricted to other endpoints (e.g. Text to Speech only) calling Speech to Text.
    "missing_permissions": ProviderNotConfigured,
}


def classify_error(response: httpx.Response) -> ProviderError | None:
    try:
        body = response.json()
    except ValueError:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    if not isinstance(detail, dict):
        return None
    # Check both fields: e.g. {"code": "invalid_api_key", "status": "api_key_id_used_as_api_key"}.
    for code in (detail.get("status"), detail.get("code")):
        error_class = _ERRORS.get(code) if isinstance(code, str) else None
        if error_class is not None:
            reason = "credentials_rejected" if code == "invalid_api_key" else code
            return error_class(reason, retry_after_seconds=http.retry_after(response))
    if detail.get("type") == "authentication_error":
        return ProviderNotConfigured("credentials_rejected")
    if detail.get("type") == "payment_required":
        return ProviderNotConfigured("paid_plan_required")
    return None

"""Provider error taxonomy shared by every AI/audio adapter (AI-01, AI-03).

Callers can always tell these apart:
- ProviderNotConfigured  — no provider selected, missing key, or credentials rejected
- ProviderLimitReached   — the provider's usage limit / rate limit was hit
- ProviderUnavailable    — timeout, network failure, or provider-side error
- ProviderInvalidOutput  — the provider answered, but the result failed validation

None of these carries request payloads (audio, transcripts, text) — only safe reasons.
"""

from __future__ import annotations


class ProviderError(Exception):
    code = "ai_provider_unavailable"
    status_code = 502

    def __init__(self, reason: str = "", *, retry_after_seconds: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds


class ProviderNotConfigured(ProviderError):
    code = "ai_provider_not_configured"
    status_code = 503


class ProviderLimitReached(ProviderError):
    code = "ai_provider_limit_reached"
    status_code = 429


class ProviderUnavailable(ProviderError):
    code = "ai_provider_unavailable"
    status_code = 502


class ProviderInvalidOutput(ProviderError):
    code = "ai_output_invalid"
    status_code = 502

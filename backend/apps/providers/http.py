"""HTTP calls to external providers with bounded timeouts and retries (AI-03).

- Each attempt has a timeout of settings.AI_PROVIDER_TIMEOUT_SECONDS.
- Network errors, timeouts and 500/502/503/504 are retried up to
  settings.AI_PROVIDER_MAX_RETRIES times with short exponential backoff.
- 429 → ProviderLimitReached (not retried: it is a usage limit).
- 401/403 → ProviderNotConfigured (credentials rejected).
- Other 4xx → ProviderUnavailable (not retried).
- An adapter may pass ``classify_error`` to map a provider's own error codes first
  (e.g. ElevenLabs reports an exhausted quota as 401 ``quota_exceeded``).
Logs contain the provider name, status and reason only — never request or response bodies.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx
from django.conf import settings

from .errors import ProviderError, ProviderLimitReached, ProviderNotConfigured, ProviderUnavailable

logger = logging.getLogger(__name__)

RETRY_STATUSES = {500, 502, 503, 504}
_sleep = time.sleep  # patched in tests


def default_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(settings.AI_PROVIDER_TIMEOUT_SECONDS))


def retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After", "")
    return int(value) if value.isdigit() else None


def post(
    client: httpx.Client,
    url: str,
    *,
    provider: str,
    headers: dict[str, str],
    json: Any = None,
    content: bytes | str | None = None,
    classify_error: Callable[[httpx.Response], ProviderError | None] | None = None,
) -> httpx.Response:
    attempts = 1 + max(0, int(settings.AI_PROVIDER_MAX_RETRIES))
    reason = "unknown"
    for attempt in range(attempts):
        if attempt:
            _sleep(min(0.5 * (2 ** (attempt - 1)), 4.0))
        try:
            response = client.post(url, headers=headers, json=json, content=content)
        except httpx.TimeoutException:
            reason = "timeout"
            logger.warning("Provider %s: attempt %d timed out.", provider, attempt + 1)
            continue
        except httpx.TransportError as exc:
            reason = "network_error"
            logger.warning("Provider %s: attempt %d network error (%s).", provider, attempt + 1, type(exc).__name__)
            continue

        status = response.status_code
        if status < 400:
            return response
        if classify_error is not None:
            error = classify_error(response)
            if error is not None:
                logger.warning("Provider %s: request failed (%d, %s).", provider, status, error.reason)
                raise error
        if status == 429:
            logger.warning("Provider %s: usage limit reached (429).", provider)
            raise ProviderLimitReached("provider_rate_limited", retry_after_seconds=retry_after(response))
        if status in (401, 403):
            logger.warning("Provider %s: credentials rejected (%d).", provider, status)
            raise ProviderNotConfigured("credentials_rejected")
        if status in RETRY_STATUSES:
            reason = f"http_{status}"
            logger.warning("Provider %s: attempt %d failed (%d).", provider, attempt + 1, status)
            continue
        logger.warning("Provider %s: request rejected (%d).", provider, status)
        raise ProviderUnavailable(f"http_{status}")

    raise ProviderUnavailable(reason)

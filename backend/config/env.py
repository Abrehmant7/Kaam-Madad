"""Small, dependency-free helpers for reading typed environment variables.

Values in the real process environment always win. The repository-root ``.env``
file is loaded by ``config.settings.base`` without overriding existing values.
Error messages name the variable but never echo values that could be secrets.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from django.core.exceptions import ImproperlyConfigured

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def env_str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip()


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ImproperlyConfigured(f"{name} must be true or false.")


def env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a whole number.") from exc
    if minimum is not None and value < minimum:
        raise ImproperlyConfigured(f"{name} must be at least {minimum}.")
    return value


def env_choice(name: str, choices: Iterable[str], default: str | None = None) -> str | None:
    """Read a variable that must be one of ``choices`` (case-insensitive)."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    allowed = sorted(choices)
    if value not in allowed:
        raise ImproperlyConfigured(f"{name} must be one of: {', '.join(allowed)}.")
    return value


DEPLOYMENT_MODE_LIVE = "live"
DEPLOYMENT_MODE_DEMO = "demo"
PHONE_PROVIDER_DEMO = "demo"
PHONE_PROVIDER_UNCONFIGURED = "unconfigured"


AI_PROVIDER_FIXTURE = "fixture"
# Simulated provider values that only a demo deployment may use (fixture AI/OCR, demo identity registry).
SIMULATED_PROVIDER_VALUES = {AI_PROVIDER_FIXTURE, "demo_registry"}


def check_simulation_allowed(
    deployment_mode: str, phone_provider: str, ai_providers: dict[str, str | None] | None = None
) -> None:
    """Simulated authentication and fixture AI results are only allowed in an explicitly
    demo deployment (AUTH-03, AI-01, NFR-04)."""
    if phone_provider == PHONE_PROVIDER_DEMO and deployment_mode != DEPLOYMENT_MODE_DEMO:
        raise ImproperlyConfigured(
            "PHONE_VERIFICATION_PROVIDER=demo (simulated phone codes) is only allowed when "
            "APP_DEPLOYMENT_MODE=demo. Live deployments must use a real provider or 'unconfigured'."
        )
    for setting_name, value in (ai_providers or {}).items():
        if value in SIMULATED_PROVIDER_VALUES and deployment_mode != DEPLOYMENT_MODE_DEMO:
            raise ImproperlyConfigured(
                f"{setting_name}={value} (simulated results) is only allowed when APP_DEPLOYMENT_MODE=demo. "
                "Live deployments must use a real provider or 'unconfigured'."
            )


def env_list(name: str, default: Iterable[str] = ()) -> list[str]:
    """Parse a comma-separated variable into a list, ignoring blank items."""
    raw = os.environ.get(name)
    if raw is None:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]

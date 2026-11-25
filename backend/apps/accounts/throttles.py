"""Rate limits for authentication and phone codes (SEC-01).

Rates come from ``settings.API_THROTTLE_RATES`` at request time (so they can be
changed per environment and in tests). Counters live in the shared database
cache, so limits hold across server processes.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from rest_framework.throttling import SimpleRateThrottle

from .phone import normalize_pk_mobile_number


class ConfigurableRateThrottle(SimpleRateThrottle):
    def get_rate(self):
        return settings.API_THROTTLE_RATES.get(self.scope)


class _PerIPThrottle(ConfigurableRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginIPThrottle(_PerIPThrottle):
    scope = "auth_login_ip"


class SignupIPThrottle(_PerIPThrottle):
    scope = "auth_signup_ip"


class PhoneCodeIPThrottle(_PerIPThrottle):
    scope = "phone_code_ip"


class LoginPhoneThrottle(ConfigurableRateThrottle):
    """Limits attempts against one phone number from any network."""

    scope = "auth_login_phone"

    def get_cache_key(self, request, view):
        raw = request.data.get("phone_number") if hasattr(request.data, "get") else None
        if not raw:
            return None
        try:
            identity = normalize_pk_mobile_number(raw)
        except ValidationError:
            identity = str(raw).strip().lower()[:64]
        # Hash so phone numbers never appear in cache keys.
        digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
        return self.cache_format % {"scope": self.scope, "ident": digest}

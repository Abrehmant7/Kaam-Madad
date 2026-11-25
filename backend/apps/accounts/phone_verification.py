"""Phone confirmation: provider boundary and challenge service (AUTH-03).

Provider boundary
-----------------
The server generates a 6-digit code, stores only an HMAC digest, and asks a
``PhoneCodeSender`` to deliver it. Implementations:

- ``DemoPhoneCodeSender`` ("demo"): sends NOTHING. The code is returned once in
  an explicitly labelled demo response so the flow can be exercised. Allowed only
  when ``DEPLOYMENT_MODE == "demo"`` (enforced at settings load and again here).
  Confirmations made this way are recorded with method "demo" and are never
  presented as real phone-ownership verification.
- ``UnconfiguredSmsSender`` ("unconfigured"): no SMS provider is set up. Every
  request fails with ``phone_verification_unavailable`` — nothing is pretended.

A real provider implements ``PhoneCodeSender.send_code`` (call the SMS API with a
timeout, return its message ID as ``provider_reference``, raise
``PhoneVerificationUnavailable`` on failure) and is selected by a new
``PHONE_VERIFICATION_PROVIDER`` value. Phone confirmation never establishes
legal identity or trade competence.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.api.exceptions import ApiError
from config.env import DEPLOYMENT_MODE_DEMO, PHONE_PROVIDER_DEMO, PHONE_PROVIDER_UNCONFIGURED

from .models import PhoneVerificationChallenge, User

CODE_LENGTH = 6
Challenge = PhoneVerificationChallenge


# --- Errors (rendered through the shared API envelope) ------------------------


class PhoneVerificationUnavailable(ApiError):
    status_code = 503
    default_code = "phone_verification_unavailable"
    default_detail = "Phone confirmation by SMS is not available yet."


class PhoneAlreadyConfirmed(ApiError):
    status_code = 409
    default_code = "phone_already_confirmed"
    default_detail = "This phone number is already confirmed."


class ResendTooSoon(ApiError):
    status_code = 429
    default_code = "resend_too_soon"
    default_detail = "Please wait before requesting another code."


class SendLimitReached(ApiError):
    status_code = 429
    default_code = "send_limit_reached"
    default_detail = "Too many codes requested. Please try again later."


class NoActiveCode(ApiError):
    status_code = 400
    default_code = "no_active_code"
    default_detail = "There is no active code. Request a new code."


class CodeExpired(ApiError):
    status_code = 400
    default_code = "code_expired"
    default_detail = "This code has expired. Request a new code."


class CodeIncorrect(ApiError):
    status_code = 400
    default_code = "code_incorrect"
    default_detail = "The code is not correct."


class TooManyAttempts(ApiError):
    status_code = 429
    default_code = "too_many_attempts"
    default_detail = "Too many wrong codes. Request a new code."


# --- Provider boundary ----------------------------------------------------------


@dataclass(frozen=True)
class DeliveryResult:
    provider_reference: str
    # True only for the demo sender: the caller may show the code on a labelled demo screen.
    reveal_code_for_demo: bool


class PhoneCodeSender(ABC):
    provider: str  # settings value
    method: str  # stored on the user as phone_confirmation_method
    simulated: bool

    @property
    def available(self) -> bool:
        return True

    @abstractmethod
    def send_code(self, *, phone_number: str, code: str, purpose: str) -> DeliveryResult: ...


class DemoPhoneCodeSender(PhoneCodeSender):
    provider = PHONE_PROVIDER_DEMO
    method = User.PhoneConfirmationMethod.DEMO
    simulated = True

    def send_code(self, *, phone_number: str, code: str, purpose: str) -> DeliveryResult:
        # Deliberately no network call and no logging of the code.
        return DeliveryResult(provider_reference=f"demo-{uuid.uuid4().hex[:12]}", reveal_code_for_demo=True)


class UnconfiguredSmsSender(PhoneCodeSender):
    provider = PHONE_PROVIDER_UNCONFIGURED
    method = User.PhoneConfirmationMethod.SMS
    simulated = False

    @property
    def available(self) -> bool:
        return False

    def send_code(self, *, phone_number: str, code: str, purpose: str) -> DeliveryResult:
        raise PhoneVerificationUnavailable()


def get_phone_code_sender() -> PhoneCodeSender:
    provider = settings.PHONE_VERIFICATION_PROVIDER
    if provider == PHONE_PROVIDER_DEMO:
        # Defence in depth: settings validation already forbids this combination.
        if settings.DEPLOYMENT_MODE != DEPLOYMENT_MODE_DEMO:
            return UnconfiguredSmsSender()
        return DemoPhoneCodeSender()
    return UnconfiguredSmsSender()


def provider_status() -> dict:
    sender = get_phone_code_sender()
    return {"provider": sender.provider, "available": sender.available, "simulated": sender.simulated}


# --- Challenge service ------------------------------------------------------------


def _policy(name: str) -> int:
    return int(settings.PHONE_VERIFICATION_POLICY[name])


def _digest(challenge_id: uuid.UUID, purpose: str, phone_number: str, code: str) -> str:
    message = f"{challenge_id}:{purpose}:{phone_number}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(math.ceil((moment - now).total_seconds()), 0)


@dataclass(frozen=True)
class StartResult:
    challenge: Challenge
    demo_code: str | None


def _open_challenges(user: User, purpose: str):
    return Challenge.objects.filter(user=user, purpose=purpose, consumed_at__isnull=True, invalidated_at__isnull=True)


def resend_available_in(user: User, purpose: str, now: datetime | None = None) -> int:
    now = now or timezone.now()
    last = Challenge.objects.filter(user=user, purpose=purpose).order_by("-created_at").first()
    if not last:
        return 0
    return _seconds_until(last.created_at + timedelta(seconds=_policy("RESEND_COOLDOWN_SECONDS")), now)


def active_challenge(user: User, purpose: str = Challenge.Purpose.CONFIRM_PHONE) -> Challenge | None:
    challenge = _open_challenges(user, purpose).order_by("-created_at").first()
    if challenge and challenge.expires_at > timezone.now() and challenge.phone_number == user.phone_number:
        return challenge
    return None


def start_phone_confirmation(user: User) -> StartResult:
    purpose = Challenge.Purpose.CONFIRM_PHONE
    if user.phone_confirmed_at:
        raise PhoneAlreadyConfirmed()
    sender = get_phone_code_sender()
    if not sender.available:
        raise PhoneVerificationUnavailable()

    with transaction.atomic():
        # Serialise code issuance per user so limits cannot be raced.
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        now = timezone.now()
        window_start = now - timedelta(hours=1)
        recent = list(
            Challenge.objects.filter(user=user, purpose=purpose, created_at__gte=window_start).order_by("created_at")
        )
        if len(recent) >= _policy("MAX_SENDS_PER_HOUR"):
            retry = _seconds_until(recent[0].created_at + timedelta(hours=1), now)
            raise SendLimitReached(details={"retry_after_seconds": retry})
        wait = resend_available_in(user, purpose, now)
        if wait > 0:
            raise ResendTooSoon(details={"retry_after_seconds": wait})

        _open_challenges(user, purpose).update(
            invalidated_at=now, invalidation_reason=Challenge.InvalidationReason.SUPERSEDED
        )
        code = f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"
        challenge = Challenge(
            user=user,
            phone_number=user.phone_number,
            purpose=purpose,
            method=sender.method,
            created_at=now,
            expires_at=now + timedelta(seconds=_policy("CODE_TTL_SECONDS")),
            max_attempts=_policy("MAX_ATTEMPTS"),
        )
        challenge.code_digest = _digest(challenge.id, purpose, challenge.phone_number, code)
        # If delivery fails the transaction rolls back and no challenge is stored.
        result = sender.send_code(phone_number=user.phone_number, code=code, purpose=purpose)
        challenge.provider_reference = result.provider_reference
        challenge.save()

    return StartResult(challenge=challenge, demo_code=code if result.reveal_code_for_demo else None)


def verify_phone_confirmation(user: User, code: str) -> User:
    """Check a code. Failed attempts are persisted before the error is raised."""
    purpose = Challenge.Purpose.CONFIRM_PHONE
    outcome: ApiError | None = None

    with transaction.atomic():
        now = timezone.now()
        challenge = (
            _open_challenges(user, purpose).select_for_update().order_by("-created_at").first()
        )
        if challenge is None:
            outcome = NoActiveCode()
        elif challenge.phone_number != user.phone_number:
            challenge.invalidated_at = now
            challenge.invalidation_reason = Challenge.InvalidationReason.PHONE_CHANGED
            challenge.save(update_fields=["invalidated_at", "invalidation_reason"])
            outcome = NoActiveCode()
        elif challenge.expires_at <= now:
            challenge.invalidated_at = now
            challenge.invalidation_reason = Challenge.InvalidationReason.EXPIRED
            challenge.save(update_fields=["invalidated_at", "invalidation_reason"])
            outcome = CodeExpired()
        elif not hmac.compare_digest(
            _digest(challenge.id, purpose, challenge.phone_number, code), challenge.code_digest
        ):
            challenge.attempt_count += 1
            fields = ["attempt_count"]
            if challenge.attempt_count >= challenge.max_attempts:
                challenge.invalidated_at = now
                challenge.invalidation_reason = Challenge.InvalidationReason.TOO_MANY_ATTEMPTS
                fields += ["invalidated_at", "invalidation_reason"]
                outcome = TooManyAttempts()
            else:
                outcome = CodeIncorrect(details={"attempts_remaining": challenge.attempts_remaining})
            challenge.save(update_fields=fields)
        else:
            challenge.consumed_at = now
            challenge.save(update_fields=["consumed_at"])
            User.objects.filter(pk=user.pk).update(
                phone_confirmed_at=now, phone_confirmation_method=challenge.method
            )

    if outcome is not None:
        raise outcome
    user.refresh_from_db(fields=["phone_confirmed_at", "phone_confirmation_method"])
    return user


def challenge_payload(challenge: Challenge, user: User) -> dict:
    now = timezone.now()
    return {
        "id": str(challenge.id),
        "method": challenge.method,
        "expires_at": challenge.expires_at.isoformat(),
        "expires_in_seconds": _seconds_until(challenge.expires_at, now),
        "attempts_remaining": challenge.attempts_remaining,
        "resend_available_in_seconds": resend_available_in(user, challenge.purpose, now),
    }

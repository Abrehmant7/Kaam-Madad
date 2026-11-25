"""Custom user model (defined before the first migration, as Django requires).

Design (AUTH-01, AUTH-02, DATA-01):
- ``id`` is an opaque UUID used as both primary key and external identifier.
- ``phone_number`` is the login identity, always stored as E.164 ``+923XXXXXXXXX``
  (normalised in Python and enforced by a database check constraint).
- ``role`` is the single marketplace role (worker or customer). It is empty for
  staff-only accounts. Staff authority comes only from ``is_staff`` /
  ``is_superuser`` / Django permissions on the server, never from ``role``.
- ``is_demo`` marks fictional/test accounts so they can be labelled and kept out
  of production directories.
- CNIC is never a username or login field.
- Phone confirmation (M2) keeps status (``phone_confirmed_at``) separate from the
  method that produced it (``phone_confirmation_method``). A "demo" confirmation
  is simulated and never counts as real phone-ownership verification. Neither
  establishes legal identity or trade competence.

Suspension uses ``is_active=False`` (Django then refuses login and drops the
session's user). A richer restricted state is added in M10.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import UserManager
from .phone import (
    PK_MOBILE_E164_REGEX,
    mask_phone_number,
    normalize_pk_mobile_number,
    validate_pk_mobile_number,
)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        WORKER = "worker", _("Worker")
        CUSTOMER = "customer", _("Customer")

    class Language(models.TextChoices):
        URDU = "ur", _("Urdu")
        ENGLISH = "en", _("English")

    class PhoneConfirmationMethod(models.TextChoices):
        # Simulated code shown on a labelled demo screen; NOT proof of phone ownership.
        DEMO = "demo", _("Demo (simulated, no SMS sent)")
        # Code delivered by a real SMS provider.
        SMS = "sms", _("SMS provider")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(
        _("phone number"),
        max_length=13,
        unique=True,
        validators=[validate_pk_mobile_number],
        help_text=_("Pakistani mobile number used to log in. Stored as +923XXXXXXXXX."),
        error_messages={"unique": _("An account with this phone number already exists.")},
    )
    role = models.CharField(
        _("marketplace role"),
        max_length=16,
        choices=Role.choices,
        blank=True,
        default="",
        help_text=_(
            "Worker or customer. Leave empty for staff-only accounts. "
            "This does not grant any staff permission."
        ),
    )
    preferred_language = models.CharField(
        _("preferred language"),
        max_length=2,
        choices=Language.choices,
        default=Language.URDU,
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Inactive accounts cannot log in. Prefer this over deleting accounts."),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Allows logging in to the staff admin site."),
    )
    is_demo = models.BooleanField(
        _("demo account"),
        default=False,
        help_text=_("Fictional/test account for demonstrations. Always shown with a demo label."),
    )
    phone_confirmed_at = models.DateTimeField(
        _("phone confirmed at"),
        null=True,
        blank=True,
        help_text=_("When the phone number was confirmed. Empty = not confirmed."),
    )
    phone_confirmation_method = models.CharField(
        _("phone confirmation method"),
        max_length=8,
        choices=PhoneConfirmationMethod.choices,
        blank=True,
        default="",
        help_text=_("How the phone was confirmed. 'Demo' is simulated and is not real verification."),
    )
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        constraints = [
            models.CheckConstraint(
                condition=Q(phone_number__regex=PK_MOBILE_E164_REGEX),
                name="accounts_user_phone_e164_pk_mobile",
                violation_error_message=_("Phone number must be stored as +923XXXXXXXXX."),
            ),
            models.CheckConstraint(
                condition=Q(role__in=["", "worker", "customer"]),
                name="accounts_user_role_valid",
            ),
            models.CheckConstraint(
                condition=Q(preferred_language__in=["ur", "en"]),
                name="accounts_user_language_valid",
            ),
            # Confirmed ⇔ a method is recorded; unconfirmed ⇔ no method.
            models.CheckConstraint(
                condition=(
                    Q(phone_confirmed_at__isnull=True, phone_confirmation_method="")
                    | Q(phone_confirmed_at__isnull=False, phone_confirmation_method__in=["demo", "sms"])
                ),
                name="accounts_user_phone_confirmation_consistent",
            ),
        ]

    def __str__(self) -> str:
        # Masked: user objects appear in admin messages, logs and select widgets.
        return self.masked_phone_number

    @property
    def phone_confirmation_status(self) -> str:
        return "confirmed" if self.phone_confirmed_at else "unconfirmed"

    @property
    def masked_phone_number(self) -> str:
        return mask_phone_number(self.phone_number)

    @property
    def is_worker(self) -> bool:
        return self.role == self.Role.WORKER

    @property
    def is_customer(self) -> bool:
        return self.role == self.Role.CUSTOMER

    def clean(self) -> None:
        super().clean()
        if self.phone_number:
            try:
                self.phone_number = normalize_pk_mobile_number(self.phone_number)
            except ValidationError as exc:
                raise ValidationError({"phone_number": exc.error_list}) from exc

    def save(self, *args, **kwargs) -> None:
        # Normalise whenever possible; anything else is rejected by the DB constraint.
        if self.phone_number:
            try:
                self.phone_number = normalize_pk_mobile_number(self.phone_number)
            except ValidationError:
                pass
        super().save(*args, **kwargs)


class PhoneVerificationChallenge(models.Model):
    """One issued phone confirmation code (AUTH-03).

    Only an HMAC digest of the code is stored. A challenge is bound to the user,
    the phone number at issue time, and a purpose. Issuing a new code invalidates
    ("supersedes") any open one; at most one open challenge exists per user and
    purpose (partial unique constraint). Codes are never logged.
    """

    class Purpose(models.TextChoices):
        CONFIRM_PHONE = "confirm_phone", _("Confirm phone number")

    class InvalidationReason(models.TextChoices):
        SUPERSEDED = "superseded", _("Superseded by a newer code")
        TOO_MANY_ATTEMPTS = "too_many_attempts", _("Too many wrong attempts")
        EXPIRED = "expired", _("Expired")
        PHONE_CHANGED = "phone_changed", _("Phone number changed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="phone_challenges")
    phone_number = models.CharField(max_length=13)
    purpose = models.CharField(max_length=32, choices=Purpose.choices)
    method = models.CharField(max_length=8, choices=User.PhoneConfirmationMethod.choices)
    code_digest = models.CharField(max_length=64)
    provider_reference = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    invalidation_reason = models.CharField(
        max_length=32, choices=InvalidationReason.choices, blank=True, default=""
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "purpose", "created_at"], name="accounts_pvc_user_purpose_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "purpose"],
                condition=Q(consumed_at__isnull=True, invalidated_at__isnull=True),
                name="accounts_pvc_one_open_per_user_purpose",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=models.F("created_at")),
                name="accounts_pvc_expires_after_created",
            ),
            models.CheckConstraint(
                condition=Q(attempt_count__lte=models.F("max_attempts")),
                name="accounts_pvc_attempts_bounded",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_purpose_display()} · {mask_phone_number(self.phone_number)} · {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def is_open(self) -> bool:
        return self.consumed_at is None and self.invalidated_at is None

    @property
    def attempts_remaining(self) -> int:
        return max(self.max_attempts - self.attempt_count, 0)

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

Restricted state and phone-confirmation method are added by later modules (M2/M10).
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
        ]

    def __str__(self) -> str:
        # Masked: user objects appear in admin messages, logs and select widgets.
        return self.masked_phone_number

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

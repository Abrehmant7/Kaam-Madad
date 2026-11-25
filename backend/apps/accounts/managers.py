from __future__ import annotations

from django.contrib.auth.base_user import BaseUserManager
from django.core.exceptions import ValidationError

from .phone import normalize_pk_mobile_number


class UserManager(BaseUserManager):
    """Manager for the phone-number-based user model.

    Passwords are hashed with Django's configured hashers (``set_password``);
    ``password=None`` creates an account with an unusable password.
    Marketplace signup (M2) must use a dedicated service that never sets staff flags.
    """

    use_in_migrations = True

    def _create_user(self, phone_number, password, **extra_fields):
        if not phone_number:
            raise ValueError("A phone number is required.")
        user = self.model(phone_number=normalize_pk_mobile_number(phone_number), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone_number, password, **extra_fields)

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(phone_number, password, **extra_fields)

    def get_by_natural_key(self, phone_number):
        """Look up a user by phone number typed in any accepted format."""
        try:
            normalized = normalize_pk_mobile_number(phone_number)
        except ValidationError:
            raise self.model.DoesNotExist("No user with that phone number.") from None
        return self.get(phone_number=normalized)

    async def aget_by_natural_key(self, phone_number):
        try:
            normalized = normalize_pk_mobile_number(phone_number)
        except ValidationError:
            raise self.model.DoesNotExist("No user with that phone number.") from None
        return await self.aget(phone_number=normalized)

"""Request validation and response shapes for account endpoints."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from .models import User
from .phone import INVALID_PHONE_CODE, INVALID_PHONE_MESSAGE, normalize_pk_mobile_number


class StrictFieldsMixin:
    """Reject any field the endpoint does not accept (e.g. is_staff, role on profile updates).

    Ignoring unknown fields would hide privilege-escalation attempts and client bugs.
    """

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError(
                    {name: [ErrorDetail("This field is not accepted.", code="unexpected_field")] for name in unknown}
                )
        return super().to_internal_value(data)


def _phone_or_error(value: str) -> str:
    try:
        return normalize_pk_mobile_number(value)
    except DjangoValidationError:
        raise serializers.ValidationError(str(INVALID_PHONE_MESSAGE), code=INVALID_PHONE_CODE) from None


class SignupSerializer(StrictFieldsMixin, serializers.Serializer):
    phone_number = serializers.CharField(max_length=40)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    password_confirm = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    role = serializers.ChoiceField(choices=[User.Role.WORKER, User.Role.CUSTOMER])
    preferred_language = serializers.ChoiceField(choices=User.Language.choices, default=User.Language.URDU)

    def validate_phone_number(self, value: str) -> str:
        normalized = _phone_or_error(value)
        if User.objects.filter(phone_number=normalized).exists():
            raise serializers.ValidationError("An account with this phone number already exists.", code="phone_taken")
        return normalized

    def validate(self, attrs):
        errors: dict[str, list[ErrorDetail]] = {}
        if attrs["password"] != attrs["password_confirm"]:
            errors["password_confirm"] = [ErrorDetail("The passwords do not match.", code="password_mismatch")]
        candidate = User(phone_number=attrs["phone_number"], role=attrs["role"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            errors["password"] = [
                ErrorDetail(str(message), code=error.code or "invalid_password")
                for error in exc.error_list
                for message in error.messages
            ]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class LoginSerializer(StrictFieldsMixin, serializers.Serializer):
    phone_number = serializers.CharField(max_length=40)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate_phone_number(self, value: str) -> str:
        return _phone_or_error(value)


class LanguagePreferenceSerializer(StrictFieldsMixin, serializers.Serializer):
    preferred_language = serializers.ChoiceField(choices=User.Language.choices)


_CODE_PATTERN = re.compile(r"^[0-9]{6}$")


class PhoneCodeSerializer(StrictFieldsMixin, serializers.Serializer):
    code = serializers.CharField(max_length=20)

    def validate_code(self, value: str) -> str:
        # Accept Urdu/Arabic-Indic digits and stray spaces typed on phone keyboards.
        digits = []
        for character in value:
            if character.isspace():
                continue
            digit = unicodedata.decimal(character, None)
            if digit is None:
                raise serializers.ValidationError("Enter the 6-digit code.", code="invalid_code_format")
            digits.append(str(digit))
        code = "".join(digits)
        if not _CODE_PATTERN.match(code):
            raise serializers.ValidationError("Enter the 6-digit code.", code="invalid_code_format")
        return code


def user_payload(user: User) -> dict:
    """Public representation of the signed-in user. Phone number is masked."""
    return {
        "id": str(user.id),
        "phone_number_masked": user.masked_phone_number,
        "role": user.role or None,
        "preferred_language": user.preferred_language,
        "is_demo": user.is_demo,
        "is_staff": user.is_staff,
        "phone_confirmation": {
            "status": user.phone_confirmation_status,
            "method": user.phone_confirmation_method or None,
            "confirmed_at": user.phone_confirmed_at.isoformat() if user.phone_confirmed_at else None,
        },
        "date_joined": user.date_joined.isoformat(),
    }

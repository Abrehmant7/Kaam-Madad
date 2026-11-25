"""Pakistani mobile number normalisation and masking (AUTH-02).

Every stored phone number is in E.164 form ``+923XXXXXXXXX`` (country code 92,
mobile prefix 3, nine further digits). Input is accepted in the forms people
actually type, including Urdu (Extended Arabic-Indic) and Arabic-Indic digits:

    0300 1234567   0300-1234567   03001234567   3001234567
    +92 300 1234567   923001234567   00923001234567   +92 0300 1234567
    ۰۳۰۰۱۲۳۴۵۶۷

Only mobile numbers are accepted because the phone number is the login identity
and the future OTP target. A phone number never establishes legal identity.
"""

from __future__ import annotations

import re
import unicodedata

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Stored form; also used by the database check constraint.
PK_MOBILE_E164_REGEX = r"^\+923[0-9]{9}$"

INVALID_PHONE_CODE = "invalid_pk_mobile"
INVALID_PHONE_MESSAGE = _("Enter a valid Pakistani mobile number, for example 0300 1234567.")

# Spaces, dashes, dots, brackets, and invisible bidi/direction marks that RTL
# keyboards and copy-paste commonly insert around numbers.
_IGNORED_CHARACTERS = re.compile(r"[\s\-().‎‏‪-‮⁦-⁩؜]")
_NATIONAL_MOBILE = re.compile(r"^3[0-9]{9}$")
# Generous bound for formatted input; anything longer is not a phone number.
_MAX_INPUT_LENGTH = 40


def _invalid() -> ValidationError:
    return ValidationError(INVALID_PHONE_MESSAGE, code=INVALID_PHONE_CODE)


def _to_ascii_digits(value: str) -> str:
    """Convert any Unicode decimal digits to ASCII; keep a leading '+'; reject anything else."""
    output = []
    for index, character in enumerate(value):
        if character == "+" and index == 0:
            output.append(character)
            continue
        digit = unicodedata.decimal(character, None)
        if digit is None:
            raise _invalid()
        output.append(str(digit))
    return "".join(output)


def normalize_pk_mobile_number(raw: object) -> str:
    """Return the E.164 form of a Pakistani mobile number or raise ValidationError."""
    if raw is None:
        raise _invalid()
    raw_text = str(raw)
    if len(raw_text) > _MAX_INPUT_LENGTH:
        raise _invalid()
    value = _IGNORED_CHARACTERS.sub("", raw_text)
    if not value:
        raise _invalid()
    value = _to_ascii_digits(value)

    if value.startswith("+"):
        international = value[1:]
    elif value.startswith("00"):
        international = value[2:]
    elif value.startswith("92") and len(value) == 12:
        international = value
    else:
        international = None

    if international is not None:
        if not international.startswith("92"):
            raise _invalid()
        national = international[2:]
        # Common mistake: keeping the trunk "0" after the country code (+92 0300...).
        if len(national) == 11 and national.startswith("0"):
            national = national[1:]
    elif value.startswith("0"):
        national = value[1:]
    else:
        national = value

    if not _NATIONAL_MOBILE.match(national):
        raise _invalid()
    return f"+92{national}"


def validate_pk_mobile_number(value: object) -> None:
    """Model/form validator: accepts any input that normalises successfully."""
    normalize_pk_mobile_number(value)


def mask_phone_number(phone_number: str | None) -> str:
    """Mask a stored number for display, keeping only the last four digits.

    ``+923001234567`` → ``+92 3** ***4567``
    """
    if not phone_number:
        return ""
    digits = re.sub(r"[^0-9]", "", phone_number)
    if len(digits) < 4:
        return "****"
    return f"+92 3** ***{digits[-4:]}"

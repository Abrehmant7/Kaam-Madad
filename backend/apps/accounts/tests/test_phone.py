from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.accounts.phone import INVALID_PHONE_CODE, mask_phone_number, normalize_pk_mobile_number

EXPECTED = "+923001234567"


class NormalizePakistaniMobileNumberTests(SimpleTestCase):
    def test_accepts_common_formats(self):
        accepted = [
            "03001234567",
            "0300 1234567",
            "0300-1234567",
            "  0300 123 4567  ",
            "3001234567",
            "+923001234567",
            "+92 300 1234567",
            "+92-300-1234567",
            "(0300) 1234567",
            "923001234567",
            "00923001234567",
            "+92 0300 1234567",  # trunk zero kept after country code
        ]
        for raw in accepted:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_pk_mobile_number(raw), EXPECTED)

    def test_accepts_urdu_and_arabic_indic_digits(self):
        self.assertEqual(normalize_pk_mobile_number("۰۳۰۰۱۲۳۴۵۶۷"), EXPECTED)  # Urdu (Extended Arabic-Indic)
        self.assertEqual(normalize_pk_mobile_number("٠٣٠٠١٢٣٤٥٦٧"), EXPECTED)  # Arabic-Indic
        self.assertEqual(normalize_pk_mobile_number("+۹۲ ۳۰۰ ۱۲۳۴۵۶۷"), EXPECTED)

    def test_ignores_invisible_direction_marks(self):
        self.assertEqual(normalize_pk_mobile_number("‎0300‏-1234567⁩"), EXPECTED)

    def test_rejects_invalid_numbers(self):
        rejected = [
            "",
            "   ",
            None,
            "0512345678",  # Islamabad landline
            "051 2345678",
            "0300123456",  # too short
            "030012345678",  # too long
            "+14155550123",  # not Pakistan
            "+92 51 2345678",  # Pakistani landline
            "0300-12a4567",
            "abc",
            "92300123456",
            "+",
            "0" * 100,
        ]
        for raw in rejected:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError) as ctx:
                    normalize_pk_mobile_number(raw)
                self.assertEqual(ctx.exception.code, INVALID_PHONE_CODE)


class MaskPhoneNumberTests(SimpleTestCase):
    def test_masks_all_but_last_four_digits(self):
        masked = mask_phone_number("+923001234567")
        self.assertEqual(masked, "+92 3** ***4567")
        self.assertNotIn("300123", masked)

    def test_empty(self):
        self.assertEqual(mask_phone_number(""), "")
        self.assertEqual(mask_phone_number(None), "")

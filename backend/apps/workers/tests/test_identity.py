import io
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock, skipUnless

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.providers import identity as ocr_module
from apps.providers.errors import ProviderNotConfigured, ProviderUnavailable
from apps.providers.identity import CnicOcrResult, TesseractCnicOcr, extract_name, extract_number
from apps.workers import identity
from apps.workers.eligibility import worker_eligibility
from apps.workers.models import DemoIdentityRecord, IdentityVerification

from .helpers import CARDS, User, WorkerApiTestCase

BACKEND_DIR = Path(__file__).resolve().parents[3]


def png(width=900, height=560, color=(250, 250, 250)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def stub_ocr(name=None, number=None):
    """Replace the OCR provider (API tests do not depend on the Tesseract binary)."""
    provider = mock.Mock()
    provider.extract.return_value = CnicOcrResult(name=name, cnic_number=number, provider="tesseract", engine="stub")
    return mock.patch("apps.providers.registry.cnic_ocr", return_value=provider)


def tesseract_available() -> bool:
    try:
        ocr_module.resolve_tesseract()
        return True
    except ProviderNotConfigured:
        return False


class CardParsingTests(SimpleTestCase):
    def test_number_candidates(self):
        self.assertEqual(extract_number("Identity Number\n00000-1234567-1  31.12.2030"), "0000012345671")
        self.assertEqual(extract_number("0000012345671"), "0000012345671")
        self.assertEqual(extract_number("OOOOO-1234567-1"), "0000012345671")  # O read for 0
        self.assertIsNone(extract_number("12345-123456-1"))  # 12 digits
        self.assertIsNone(extract_number("00000-1234567-1\n00000-7654321-2"))  # ambiguous
        self.assertEqual(extract_number("00000-1234567-1 and again 00000 1234567 1"), "0000012345671")

    def test_name_from_labelled_field(self):
        text = "DEMO CARD\nName\nBilal Ahmed\nFather Name\nAhmed Raza\nIdentity Number\n00000-1234567-1"
        self.assertEqual(extract_name(text), "Bilal Ahmed")
        self.assertEqual(extract_name("Name: Sana Tariq\nFather Name: Tariq Mehmood"), "Sana Tariq")
        self.assertIsNone(extract_name("Father Name\nAhmed Raza"))  # only the father's name
        self.assertIsNone(extract_name("Bilal Ahmed\n00000-1234567-1"))  # no label
        self.assertIsNone(extract_name("Name\n00000-1234567-1"))  # digits are not a name
        self.assertIsNone(extract_name("Name\nBilal Ahmed\nName\nKamran Shah"))  # ambiguous


@override_settings(TESSERACT_CMD="tesseract", TESSERACT_LANG="eng", OCR_TIMEOUT_SECONDS=10)
class TesseractAdapterTests(SimpleTestCase):
    def setUp(self):
        ocr_module._RESOLVED.clear()
        self.addCleanup(ocr_module._RESOLVED.clear)

    def test_missing_executable_is_a_setup_error(self):
        with override_settings(TESSERACT_CMD="definitely-not-tesseract-xyz"), \
                mock.patch.object(ocr_module, "WINDOWS_DEFAULT", Path("Z:/missing/tesseract.exe")):
            with self.assertRaises(ProviderNotConfigured) as caught:
                TesseractCnicOcr()
        self.assertEqual(caught.exception.reason, "tesseract_not_found")

    def test_command_line_temp_files_and_rotation_retry(self):
        seen, folders = [], []

        def fake_run(args, **kwargs):
            if args[1] in ("--version", "--list-langs"):
                return subprocess.CompletedProcess(args, 0, stdout="tesseract v5.4.0\neng\nosd\n", stderr="")
            image = Path(args[1])
            self.assertTrue(image.exists())
            folders.append(image.parent)
            seen.append(args)
            text = b"" if len(seen) == 1 else b"Name\nSana Tariq\nIdentity Number\n00000-7654321-2\n"
            return subprocess.CompletedProcess(args, 0, stdout=text, stderr=b"")

        with mock.patch.object(ocr_module.shutil, "which", return_value="/usr/bin/tesseract"), \
                mock.patch.object(ocr_module.subprocess, "run", side_effect=fake_run):
            result = TesseractCnicOcr().extract(image=png(), mime_type="image/png")
        self.assertEqual(result.status, "read")
        self.assertEqual((result.name, result.cnic_number, result.rotation), ("Sana Tariq", "0000076543212", 90))
        self.assertEqual(seen[0][2:], ["stdout", "-l", "eng", "--psm", "6"])
        self.assertTrue(all(not folder.exists() for folder in folders))  # temporary images deleted

    def test_language_data_missing(self):
        def fake_run(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout="tesseract v5\nosd\n", stderr="")

        with mock.patch.object(ocr_module.shutil, "which", return_value="/usr/bin/tesseract"), \
                mock.patch.object(ocr_module.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(ProviderNotConfigured) as caught:
                TesseractCnicOcr()
        self.assertEqual(caught.exception.reason, "tesseract_language_missing")

    def test_timeout_is_bounded(self):
        def fake_run(args, **kwargs):
            if args[1] in ("--version", "--list-langs"):
                return subprocess.CompletedProcess(args, 0, stdout="tesseract v5\neng\n", stderr="")
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])

        with mock.patch.object(ocr_module.shutil, "which", return_value="/usr/bin/tesseract"), \
                mock.patch.object(ocr_module.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(ProviderUnavailable) as caught:
                TesseractCnicOcr().extract(image=png(), mime_type="image/png")
        self.assertEqual(caught.exception.reason, "ocr_timeout")


@skipUnless(tesseract_available(), "Tesseract executable not installed on this host")
class RealTesseractTests(SimpleTestCase):
    """Runs the REAL Tesseract executable on the synthetic DEMO cards (no mocks)."""

    def read(self, filename):
        return TesseractCnicOcr().extract(image=(CARDS / filename).read_bytes(), mime_type="")

    def test_distinct_cards_give_distinct_fields(self):
        bilal = self.read("demo-card-bilal-ahmed.png")
        sana = self.read("demo-card-sana-tariq.png")
        self.assertEqual((bilal.name, bilal.cnic_number), ("Bilal Ahmed", "0000012345671"))
        self.assertEqual((sana.name, sana.cnic_number), ("Sana Tariq", "0000076543212"))

    def test_rotated_photo_is_turned_and_read(self):
        result = self.read("demo-card-sana-tariq-rotated.jpg")
        self.assertEqual((result.name, result.cnic_number), ("Sana Tariq", "0000076543212"))
        self.assertNotEqual(result.rotation, 0)

    def test_blurred_card_is_unreadable(self):
        self.assertEqual(self.read("demo-card-unreadable.jpg").status, "unreadable")


class IdentityFlowTests(WorkerApiTestCase):
    def start(self, client=None, consent=True):
        return (client or self.client).post(reverse("identity-cases"), {"consent": consent}, format="json")

    def scan(self, case_id, data: bytes | None = None, name="card.png", client=None):
        return (client or self.client).post(
            reverse("identity-scan", args=[case_id]),
            {"image": SimpleUploadedFile(name, data if data is not None else png(), content_type="image/png")},
            format="multipart",
        )

    def submit(self, case_id, name, number, client=None):
        return (client or self.client).post(
            reverse("identity-submit", args=[case_id]), {"name": name, "cnic_number": number}, format="json"
        )

    def test_consent_is_required(self):
        response = self.start(consent=False)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["fields"]["consent"][0]["code"], "consent_required")
        self.assertFalse(IdentityVerification.objects.exists())

    def test_match_requires_name_and_number_of_the_same_record(self):
        self.complete_profile()
        case_id = self.start().json()["case"]["id"]
        with stub_ocr("Bilal Ahmed", "0000012345671"), self.assertLogs("apps.workers", level="INFO") as logs:
            scanned = self.scan(case_id)
            self.assertEqual(scanned.status_code, 200, scanned.content)
            ocr = scanned.json()["case"]["ocr"]
            self.assertEqual((ocr["status"], ocr["name"], ocr["cnic_number"]), ("read", "Bilal Ahmed", "00000-1234567-1"))
            self.assertEqual(scanned.json()["case"]["status"], "in_progress")  # OCR alone never approves
            # Harmless differences in case, spacing and dashes.
            result = self.submit(case_id, "  bilal   AHMED ", "0000012345671")
        self.assertEqual(result.status_code, 200, result.content)
        case = result.json()["case"]
        self.assertEqual(case["status"], "demo_approved")
        self.assertEqual(case["registry"]["outcome"], "match")
        self.assertEqual(case["registry"]["reference"], "DEMO-REG-0001")
        self.assertEqual(case["registry"]["demo_address"], "House 12, Street 4, Demo Town, Islamabad")
        self.assertEqual(case["masked_cnic"], "*****-*****67-1")
        self.assertEqual(case["review"], {**case["review"], "name_corrected": False, "number_corrected": False})
        self.assertIsNone(case["ocr"]["cnic_number"])  # draft cleared after approval
        self.assertEqual(result.json()["eligibility"], {"can_take_jobs": True, "receives_requests": True, "reasons": []})
        dashboard = self.me().json()
        for text in (str(dashboard), "\n".join(logs.output)):
            self.assertNotIn("0000012345671", text)
            self.assertNotIn("00000-1234567-1", text)
            self.assertNotIn("Bilal", text)
        # The demo address is never a service area.
        self.assertEqual(dashboard["profile"]["service_areas"], ["isb-g-10", "isb-g-9"])

    def test_known_number_with_a_different_name_fails(self):
        case_id = self.start().json()["case"]["id"]
        with stub_ocr("Kamran Shah", "0000012345671"):
            self.scan(case_id)
        miss = self.submit(case_id, "Kamran Shah", "00000-1234567-1")
        self.assertEqual(miss.json()["case"]["status"], "no_match")
        self.assertEqual(miss.json()["case"]["registry"]["outcome"], "name_mismatch")
        self.assertNotIn("Bilal", str(miss.json()))  # the recorded name is never revealed
        self.assertIn("identity_no_match", miss.json()["eligibility"]["reasons"])
        # A corrected name is recorded as a correction, distinct from the scan.
        retry = self.submit(case_id, "Bilal Ahmed", "00000-1234567-1").json()["case"]
        self.assertEqual(retry["status"], "demo_approved")
        self.assertTrue(retry["review"]["name_corrected"])
        self.assertFalse(retry["review"]["number_corrected"])
        self.assertEqual(retry["registry"]["attempts"], 2)

    def test_unknown_number_has_no_record_and_does_not_change_eligibility(self):
        self.complete_profile()
        case_id = self.start().json()["case"]["id"]
        with stub_ocr("Usman Ali", "0000099999999"):
            self.scan(case_id)
        miss = self.submit(case_id, "Usman Ali", "0000099999999").json()
        self.assertEqual(miss["case"]["registry"]["outcome"], "no_record")
        self.assertEqual(miss["eligibility"]["can_take_jobs"], False)
        self.assertEqual(IdentityVerification.objects.get(pk=case_id).status, "no_match")

    def test_unreadable_scan_allows_typing_and_rescan(self):
        case_id = self.start().json()["case"]["id"]
        with stub_ocr(None, None):
            body = self.scan(case_id).json()["case"]
        self.assertEqual(body["ocr"]["status"], "unreadable")
        self.assertIsNone(body["ocr"]["name"])
        with stub_ocr(None, "0000076543212"):
            self.assertEqual(self.scan(case_id).json()["case"]["ocr"]["status"], "partial")
        typed = self.submit(case_id, "Sana Tariq", "0000076543212").json()["case"]
        self.assertEqual(typed["status"], "demo_approved")
        self.assertTrue(typed["review"]["name_corrected"])  # typed, not from the scan
        self.assertEqual(typed["scan"]["count"], 2)

    def test_details_must_follow_a_processed_scan(self):
        case_id = self.start().json()["case"]["id"]
        response = self.submit(case_id, "Bilal Ahmed", "0000012345671")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "verification_scan_required")

    def test_image_validation_before_ocr(self):
        case_id = self.start().json()["case"]["id"]
        with stub_ocr("x", None) as patched:
            self.assertEqual(self.scan(case_id, b"%PDF-1.7 not an image" * 20).status_code, 415)
            self.assertEqual(self.scan(case_id, png()[:300]).status_code, 415)  # truncated
            small = self.scan(case_id, png(200, 120))
            self.assertEqual((small.status_code, small.json()["error"]["code"]), (400, "image_dimensions"))
            with override_settings(IDENTITY_LIMITS={"MAX_IMAGE_BYTES": 1000, "MIN_IMAGE_BYTES": 200, "MIN_WIDTH": 400,
                                                    "MIN_HEIGHT": 250, "MAX_PIXELS": 40_000_000}):
                self.assertEqual(self.scan(case_id, png()).status_code, 413)
            with override_settings(IDENTITY_LIMITS={"MAX_IMAGE_BYTES": 5_000_000, "MIN_IMAGE_BYTES": 200, "MIN_WIDTH": 400,
                                                    "MIN_HEIGHT": 250, "MAX_PIXELS": 100_000}):
                self.assertEqual(self.scan(case_id, png()).json()["error"]["code"], "image_dimensions")
            patched.return_value.extract.assert_not_called()
        self.assertEqual(self.client.post(reverse("identity-scan", args=[case_id]), {}, format="multipart").status_code, 400)

    def test_scans_are_not_stored(self):
        case_id = self.start().json()["case"]["id"]
        before = {str(path) for path in Path(self._media).rglob("*")}
        with stub_ocr("Bilal Ahmed", "0000012345671"):
            self.scan(case_id, (CARDS / "demo-card-bilal-ahmed.png").read_bytes())
        self.assertEqual({str(path) for path in Path(self._media).rglob("*")}, before)

    def test_invalid_details(self):
        case_id = self.start().json()["case"]["id"]
        for name, number, field, code in (
            ("Bilal Ahmed", "12345", "cnic_number", "invalid_cnic"),
            ("Bilal Ahmed", "00000-1234567-12", "cnic_number", "invalid_cnic"),
            ("B1lal", "0000012345671", "name", "invalid_name"),
        ):
            with self.subTest(code=code):
                response = self.submit(case_id, name, number)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["fields"][field][0]["code"], code)

    def test_tesseract_setup_error_is_reported(self):
        case_id = self.start().json()["case"]["id"]
        with mock.patch("apps.providers.registry.cnic_ocr", side_effect=ProviderNotConfigured("tesseract_not_found")):
            response = self.scan(case_id)
        self.assertEqual(response.status_code, 503)
        error = response.json()["error"]
        self.assertEqual(error["code"], "ai_provider_not_configured")
        self.assertEqual((error["details"]["capability"], error["details"]["reason"]), ("cnic_ocr", "tesseract_not_found"))
        self.assertEqual(error["details"]["case"]["ocr"]["status"], "failed")
        # A failed scan does not unlock typing-only submission.
        self.assertEqual(self.submit(case_id, "Bilal Ahmed", "0000012345671").status_code, 409)

    def test_another_account_cannot_use_the_case(self):
        case_id = self.start().json()["case"]["id"]
        with stub_ocr("Bilal Ahmed", "0000012345671"):
            self.scan(case_id)
        _, other_worker = self.other_client()
        _, customer = self.other_client("03004444444", role=User.Role.CUSTOMER)
        self.assertEqual(self.scan(case_id, client=other_worker).status_code, 404)
        self.assertEqual(self.submit(case_id, "Bilal Ahmed", "0000012345671", client=other_worker).status_code, 404)
        self.assertEqual(self.scan(case_id, client=customer).status_code, 403)
        own = other_worker.get(reverse("identity-cases")).json()
        self.assertIsNone(own["case"])  # the other worker sees only their own (none)

    def test_new_attempt_supersedes_an_unfinished_one_but_not_a_completed_check(self):
        first = self.start().json()["case"]["id"]
        second = self.start().json()["case"]["id"]
        self.assertEqual(IdentityVerification.objects.get(pk=first).status, "superseded")
        self.assertEqual(self.submit(first, "Bilal Ahmed", "0000012345671").status_code, 404)
        with stub_ocr("Bilal Ahmed", "0000012345671"):
            self.scan(second)
        self.assertEqual(self.submit(second, "Bilal Ahmed", "0000012345671").json()["case"]["status"], "demo_approved")
        self.assertEqual(self.start().status_code, 409)
        self.assertEqual(self.submit(second, "Sana Tariq", "0000076543212").status_code, 409)

    @override_settings(DEPLOYMENT_MODE="live")
    def test_live_mode_rejects_simulated_approvals(self):
        self.complete_profile()
        old = IdentityVerification.objects.create(
            user=self.worker, consent_given_at="2026-11-26T10:00:00Z", consent_version="x",
            status="demo_approved", method="demo_registry", decided_at="2026-11-26T10:00:00Z",
        )
        result = worker_eligibility(self.worker)
        self.assertFalse(result.can_take_jobs)
        self.assertIn("demo_approval_not_accepted_here", result.reasons)
        self.assertFalse(self.me().json()["identity"]["counts_here"])
        case_id = self.start().json()["case"]["id"]
        self.assertEqual(IdentityVerification.objects.get(pk=old.pk).status, "superseded")
        with stub_ocr("Bilal Ahmed", "0000012345671"):
            self.scan(case_id)
        response = self.submit(case_id, "Bilal Ahmed", "0000012345671")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "identity_provider_not_configured")
        self.assertEqual(IdentityVerification.objects.get(pk=case_id).status, "in_progress")
        with self.assertRaises(CommandError):
            call_command("seed_demo_registry")

    def test_customers_cannot_start_verification(self):
        _, customer = self.other_client("03006666666", role=User.Role.CUSTOMER)
        self.assertEqual(self.start(client=customer).status_code, 403)


class EligibilityTests(WorkerApiTestCase):
    def approve(self):
        case = identity.start_case(self.worker)
        with stub_ocr("Imran Siddiqui", "0000024681353"):
            identity.scan_card(case, png())
        identity.submit_details(case, "Imran Siddiqui", "0000024681353")
        return case

    def test_reasons(self):
        self.assertEqual(worker_eligibility(self.worker).reasons, ["profile_incomplete", "identity_not_started"])
        self.complete_profile()
        self.assertEqual(worker_eligibility(self.worker).reasons, ["identity_not_started"])
        self.approve()
        self.assertTrue(worker_eligibility(self.worker).can_take_jobs)

    def test_paused_worker_is_eligible_but_receives_no_requests(self):
        self.complete_profile()
        self.approve()
        self.client.patch(reverse("worker-preferences"), {"accepting_requests": False}, format="json")
        result = worker_eligibility(self.worker)
        self.assertTrue(result.can_take_jobs)
        self.assertFalse(result.receives_requests)
        self.assertEqual(result.reasons, ["not_accepting_requests"])

    def test_inactive_account_and_non_workers(self):
        self.complete_profile()
        self.approve()
        self.worker.is_active = False
        self.worker.save()
        self.assertIn("account_inactive", worker_eligibility(self.worker).reasons)
        customer = User.objects.create_user("03007777777", "x-Strong-2026!", role=User.Role.CUSTOMER)
        self.assertEqual(worker_eligibility(customer).reasons, ["not_a_worker"])

    def test_dashboard_usable_without_verification(self):
        self.complete_profile()
        body = self.me().json()
        self.assertEqual(body["identity"]["status"], "not_started")
        self.assertEqual(body["eligibility"], {"can_take_jobs": False, "receives_requests": False,
                                               "reasons": ["identity_not_started"]})


class DemoRegistryTests(WorkerApiTestCase):
    def test_seed_is_idempotent_and_fictional(self):
        with open(os.devnull, "w") as devnull:
            call_command("seed_demo_registry", stdout=devnull)
            call_command("seed_demo_registry", stdout=devnull)
        self.assertEqual(DemoIdentityRecord.objects.count(), 3)
        for record in DemoIdentityRecord.objects.all():
            self.assertTrue(record.cnic_masked.startswith("*****-*****"))
            self.assertTrue(record.demo_address)

    def test_helpers(self):
        self.assertEqual(identity.normalize_cnic(" 00000-1234567-1 "), "0000012345671")
        self.assertIsNone(identity.normalize_cnic("0000-0000001-1"))
        self.assertEqual(identity.mask_cnic("1234512345671"), "*****-*****67-1")
        self.assertEqual(identity.normalize_name("  Bilal   AHMED "), identity.normalize_name("bilal ahmed"))


class AdminTests(WorkerApiTestCase):
    def test_staff_admin_lists_verification_status_and_source(self):
        case = identity.start_case(self.worker)
        with stub_ocr("Bilal Ahmed", "0000012345671"):
            identity.scan_card(case, png())
        identity.submit_details(case, "Bilal Ahmed", "0000012345671")
        admin = User.objects.create_superuser("03008888888", "Admin-Pass-2026!")
        self.client.force_login(admin)
        page = self.client.get(reverse("admin:workers_identityverification_changelist")).content.decode()
        self.assertIn("tesseract (read)", page)
        self.assertIn("demo_registry (demo, fictional)", page)
        self.assertNotIn("0000012345671", page)
        detail = self.client.get(reverse("admin:workers_identityverification_change", args=[case.pk])).content.decode()
        self.assertIn("DEMO-REG-0001", detail)
        self.assertNotIn(case.cnic_digest, detail)
        self.assertNotIn("0000012345671", detail)


class StartupGuardTests(SimpleTestCase):
    def test_live_production_refuses_the_demo_registry(self):
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "DJANGO_SECRET_KEY": "x" * 30 + "-production-like-test-secret-key-0123456789",
            "DJANGO_ALLOWED_HOSTS": "example.org",
            "APP_DEPLOYMENT_MODE": "live",
            "PHONE_VERIFICATION_PROVIDER": "unconfigured",
            "SPEECH_TO_TEXT_PROVIDER": "unconfigured",
            "INTERPRETATION_PROVIDER": "unconfigured",
            "TEXT_TO_SPEECH_PROVIDER": "unconfigured",
            "IDENTITY_VERIFICATION_PROVIDER": "demo_registry",
        }
        result = subprocess.run([sys.executable, "-c", "import django; django.setup()"], cwd=BACKEND_DIR, env=env,
                                capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("IDENTITY_VERIFICATION_PROVIDER=demo_registry", result.stderr)


"""Event demo verification (pitch item 3): two SAMPLE uploads → existing demo_approved status, demo mode only."""

import io
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from apps.workers.models import IdentityVerification

from .helpers import WorkerApiTestCase

SAMPLES = Path(__file__).resolve().parents[4] / "frontend" / "public" / "demo-samples"


def upload(name: str, data: bytes | None = None, content_type="image/png"):
    data = data if data is not None else (SAMPLES / name).read_bytes()
    return SimpleUploadedFile(name, data, content_type=content_type)


def tiny_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (120, 80), (10, 10, 10)).save(buffer, "PNG")
    return buffer.getvalue()


class DemoVerificationTests(WorkerApiTestCase):
    url = reverse("identity-demo-verification")

    def post(self, cnic=None, selfie=None, client=None):
        files = {"cnic_image": cnic or upload("sample-cnic.png"), "selfie_image": selfie or upload("sample-selfie.png")}
        return (client or self.client).post(self.url, files, format="multipart")

    def test_worker_reaches_the_dashboard_before_verification(self):
        self.complete_profile()
        me = self.me().json()
        self.assertEqual(me["identity"]["status"], "not_started")
        self.assertFalse(me["eligibility"]["can_take_jobs"])

    def test_sample_images_give_demo_approval_without_ocr_or_registry(self):
        self.complete_profile()
        with mock.patch("apps.providers.registry.cnic_ocr") as ocr, \
                mock.patch("apps.workers.identity.verification_provider") as registry:
            response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        ocr.assert_not_called()
        registry.assert_not_called()
        case = response.json()["case"]
        self.assertEqual((case["status"], case["method"], case["simulated"], case["counts_here"]),
                         ("demo_approved", "demo_sample_upload", True, True))
        self.assertEqual((case["ocr"]["status"], case["registry"]["outcome"], case["masked_cnic"]), ("not_run", "not_checked", None))
        self.assertTrue(response.json()["eligibility"]["can_take_jobs"])
        stored = IdentityVerification.objects.get(user=self.worker)
        self.assertEqual((stored.cnic_digest, stored.ocr_name_pending, stored.scan_width), ("", "", 856))
        self.assertFalse(hasattr(stored, "image"))  # nothing but metadata is kept

    def test_both_uploads_are_required_and_checked_with_the_image_limits(self):
        missing = self.client.post(self.url, {"cnic_image": upload("sample-cnic.png")}, format="multipart")
        self.assertEqual(missing.status_code, 400)
        self.assertIn("selfie_image", missing.json()["error"]["fields"])
        fake = self.post(selfie=upload("selfie.png", b"not an image at all " * 20))
        self.assertEqual((fake.status_code, fake.json()["error"]["code"]), (415, "image_unsupported"))
        small = self.post(cnic=upload("card.png", tiny_png()))
        self.assertEqual(small.json()["error"]["code"], "image_dimensions")
        self.assertFalse(IdentityVerification.objects.filter(user=self.worker).exists())

    @override_settings(DEPLOYMENT_MODE="live")
    def test_refused_in_live_mode(self):
        response = self.post()
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (403, "demo_verification_unavailable"))
        self.assertFalse(IdentityVerification.objects.filter(user=self.worker).exists())

    def test_demo_approval_counts_only_in_demo_mode(self):
        self.complete_profile()
        self.assertEqual(self.post().status_code, 200)
        with override_settings(DEPLOYMENT_MODE="live"):
            me = self.me().json()
        self.assertFalse(me["identity"]["counts_here"])
        self.assertFalse(me["eligibility"]["can_take_jobs"])
        self.assertIn("demo_approval_not_accepted_here", me["eligibility"]["reasons"])

    def test_existing_records_are_preserved(self):
        self.assertEqual(self.post().status_code, 200)
        again = self.post()
        self.assertEqual(again.status_code, 409)  # already approved: nothing replaced
        self.assertEqual(IdentityVerification.objects.filter(user=self.worker).count(), 1)
        case = IdentityVerification.objects.get(user=self.worker)
        case.status = IdentityVerification.Status.SUSPENDED
        case.save()
        locked = self.post()
        self.assertEqual(locked.status_code, 409)  # a staff suspension is not bypassed
        self.assertEqual(IdentityVerification.objects.get(user=self.worker).status, "suspended")

    def test_customers_cannot_use_it(self):
        _, customer = self.other_client(phone="03003333333", role="customer")
        self.assertEqual(self.post(client=customer).status_code, 403)

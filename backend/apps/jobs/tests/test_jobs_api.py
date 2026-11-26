import io
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.jobs.models import JobPhoto, JobRequest
from apps.jobs.summary import matching_summary
from apps.providers.errors import ProviderUnavailable
from apps.voice.tests.helpers import make_wav

User = get_user_model()
KARACHI = ZoneInfo("Asia/Karachi")
PASSWORD = "Strong-Pass-2026!"


def karachi(days: int, hour: int, minute: int = 0) -> str:
    """An Asia/Karachi wall-clock time ``days`` from today, as an ISO string with +05:00."""
    day = timezone.now().astimezone(KARACHI).date() + timedelta(days=days)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=KARACHI).isoformat()


def image_bytes(fmt="JPEG", size=(640, 480), gps=False) -> bytes:
    image = Image.new("RGB", size, (200, 120, 40))
    buffer = io.BytesIO()
    if gps:
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"  # camera make
        gps_ifd = exif.get_ifd(0x8825)
        gps_ifd[1], gps_ifd[2] = "N", (33.0, 41.0, 30.0)
        gps_ifd[3], gps_ifd[4] = "E", (73.0, 2.0, 15.0)
        image.save(buffer, format=fmt, exif=exif.tobytes())
    else:
        image.save(buffer, format=fmt)
    return buffer.getvalue()


COMPLETE = {
    "description": "Install two ceiling fans in the lounge.",
    "trade": "electrician",
    "services": ["elec_fan_install"],
    "services_excluded": ["elec_ups_inverter"],
    "city": "islamabad",
    "area": "isb-g-9",
    "preferred_time_text": "",
    "address_private": "House 5, Street 9, G-9/1",
    "access_notes": "Ring the bell twice; dog in the yard.",
    "budget_pkr": "3500",
}


class JobApiTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp(prefix="kaam-madad-m5-")
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        with open(Path(tempfile.gettempdir()) / "seed-m5.log", "w") as log:
            call_command("seed_catalog", stdout=log)

    def setUp(self):
        self.customer = User.objects.create_user("03001111111", PASSWORD, role=User.Role.CUSTOMER)
        self.client = APIClient()
        self.client.force_login(self.customer)

    def other(self, phone="03002222222", role=User.Role.CUSTOMER):
        user = User.objects.create_user(phone, PASSWORD, role=role)
        client = APIClient()
        client.force_login(user)
        return user, client

    def create_text(self, text="Two fans need installing, not the UPS.", client=None):
        return (client or self.client).post(reverse("jobs"), {"source_kind": "text", "original_text": text}, format="json")

    def patch(self, job_id, data, client=None):
        return (client or self.client).patch(reverse("job", args=[job_id]), data, format="json")

    def confirm(self, job_id, client=None):
        return (client or self.client).post(reverse("job-confirm", args=[job_id]))

    def fields(self, response, name):
        return [item["code"] for item in response.json()["error"]["fields"].get(name, [])]


class TextRequestTests(JobApiTestCase):
    def test_text_request_from_creation_to_confirmation_and_reopening(self):
        created = self.create_text()
        self.assertEqual(created.status_code, 201, created.content)
        job = created.json()
        self.assertEqual(job["status"], "draft")
        self.assertEqual(job["source"]["original_text"], "Two fans need installing, not the UPS.")
        self.assertFalse(job["ready_to_confirm"])
        self.assertIn("window_start", job["issues"])

        saved = self.patch(job["id"], {**COMPLETE, "window_start": karachi(2, 17), "window_end": karachi(2, 19)})
        self.assertEqual(saved.status_code, 200, saved.content)
        body = saved.json()
        self.assertTrue(body["ready_to_confirm"])
        # Stored in UTC: 17:00 Karachi is 12:00Z.
        self.assertTrue(body["details"]["window_start"].endswith("T12:00:00Z"))
        self.assertEqual(body["details"]["budget_pkr"], "3500.00")
        self.assertEqual(body["source"]["original_text"], "Two fans need installing, not the UPS.")  # untouched

        confirmed = self.confirm(job["id"])
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        self.assertEqual(confirmed.json()["status"], "confirmed")
        self.assertFalse(confirmed.json()["already_confirmed"])

        listing = self.client.get(reverse("jobs"), {"status": "confirmed"}).json()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["results"][0]["id"], job["id"])
        self.assertNotIn("address_private", listing["results"][0])
        reopened = self.client.get(reverse("job", args=[job["id"]])).json()
        self.assertEqual(reopened["details"]["area"], "isb-g-9")
        self.assertEqual(reopened["details"]["address_private"], "House 5, Street 9, G-9/1")  # owner sees it

    def test_naive_times_are_read_as_karachi_and_stored_in_utc(self):
        job = self.create_text().json()
        start = karachi(3, 10)[:19]  # drop the offset
        end = karachi(3, 12)[:19]
        body = self.patch(job["id"], {"window_start": start, "window_end": end}).json()
        self.assertTrue(body["details"]["window_start"].endswith("T05:00:00Z"))
        stored = JobRequest.objects.get(pk=job["id"]).window_start
        self.assertEqual(stored.utcoffset(), timedelta(0))

    def test_repeated_confirmation_keeps_one_confirmed_request(self):
        job = self.create_text().json()
        self.patch(job["id"], {**COMPLETE, "window_start": karachi(1, 9), "window_end": karachi(1, 11)})
        first = self.confirm(job["id"])
        second = self.confirm(job["id"])
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertTrue(second.json()["already_confirmed"])
        self.assertEqual(first.json()["confirmed_at"], second.json()["confirmed_at"])
        self.assertEqual(JobRequest.objects.filter(customer=self.customer).count(), 1)
        self.assertEqual(JobRequest.objects.filter(status="confirmed").count(), 1)

    def test_failed_confirmation_preserves_the_draft(self):
        job = self.create_text().json()
        self.patch(job["id"], {"trade": "electrician", "services": ["elec_fan_install"], "area": "isb-g-9"})
        response = self.confirm(job["id"])
        self.assertEqual(response.status_code, 400)
        self.assertIn("required", self.fields(response, "window_start"))
        stored = JobRequest.objects.get(pk=job["id"])
        self.assertEqual(stored.status, "draft")
        self.assertEqual(stored.area.code, "isb-g-9")
        self.assertEqual(stored.city.code, "islamabad")  # derived from the area

    def test_confirmed_request_is_read_only(self):
        job = self.create_text().json()
        self.patch(job["id"], {**COMPLETE, "window_start": karachi(1, 9), "window_end": karachi(1, 11)})
        self.confirm(job["id"])
        self.assertEqual(self.patch(job["id"], {"description": "changed"}).status_code, 409)
        self.assertEqual(self.client.delete(reverse("job", args=[job["id"]])).status_code, 409)

    def test_drafts_can_be_deleted(self):
        job = self.create_text().json()
        self.assertEqual(self.client.delete(reverse("job", args=[job["id"]])).status_code, 204)
        self.assertFalse(JobRequest.objects.exists())


class ValidationTests(JobApiTestCase):
    def setUp(self):
        super().setUp()
        self.job = self.create_text().json()["id"]

    def test_invalid_catalog_relationships_are_rejected_and_nothing_is_saved(self):
        self.patch(self.job, {"description": "kept"})
        cases = [
            ({"trade": "electrician", "services": ["plmb_leak_repair"]}, "services", "service_not_in_trade"),
            ({"trade": "plumber", "services_excluded": ["elec_fan_install"]}, "services_excluded", "service_not_in_trade"),
            ({"services": ["elec_fan_install"]}, "services", "service_not_in_trade"),  # no trade chosen
            ({"trade": "electrician", "services": ["elec_fan_install"], "services_excluded": ["elec_fan_install"]},
             "services_excluded", "offered_and_excluded_overlap"),
            ({"city": "islamabad", "area": "rwp-saddar"}, "area", "area_not_in_city"),
            ({"area": "isb-nowhere"}, "area", "unknown_area"),
            ({"trade": "astronaut"}, "trade", "unknown_trade"),
            ({"description": "changed", "trade": "electrician", "services": ["nope"]}, "services", "unknown_service"),
        ]
        for payload, name, code in cases:
            with self.subTest(code=code, payload=payload):
                response = self.patch(self.job, payload)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(code, self.fields(response, name))
        self.assertEqual(JobRequest.objects.get(pk=self.job).description, "kept")

    def test_invalid_time_windows(self):
        cases = [
            ({"window_start": karachi(1, 18), "window_end": karachi(1, 17)}, "window_end", "window_end_before_start"),
            ({"window_start": karachi(1, 18), "window_end": karachi(1, 18)}, "window_end", "window_end_before_start"),
            ({"window_start": karachi(-1, 18), "window_end": karachi(-1, 19)}, "window_start", "window_in_past"),
            ({"window_start": karachi(120, 9), "window_end": karachi(120, 10)}, "window_start", "window_too_far"),
        ]
        for payload, name, code in cases:
            with self.subTest(code=code):
                response = self.patch(self.job, payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(code, self.fields(response, name))

    def test_a_window_that_has_passed_since_saving_blocks_confirmation(self):
        self.patch(self.job, {**COMPLETE, "window_start": karachi(1, 9), "window_end": karachi(1, 11)})
        with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(days=3)):
            response = self.confirm(self.job)
        self.assertEqual(response.status_code, 400)
        self.assertIn("window_in_past", self.fields(response, "window_start"))
        self.assertEqual(JobRequest.objects.get(pk=self.job).status, "draft")

    def test_budget_is_a_non_negative_decimal(self):
        self.assertEqual(self.patch(self.job, {"budget_pkr": "-5"}).status_code, 400)
        self.assertEqual(self.patch(self.job, {"budget_pkr": "1500.50"}).json()["details"]["budget_pkr"], "1500.50")
        self.assertIsNone(self.patch(self.job, {"budget_pkr": None}).json()["details"]["budget_pkr"])

    def test_unknown_fields_are_rejected(self):
        self.assertEqual(self.patch(self.job, {"status": "confirmed"}).status_code, 400)
        self.assertEqual(self.patch(self.job, {"customer": "x"}).status_code, 400)


class VoiceRequestTests(JobApiTestCase):
    def voice_source(self, client=None):
        client = client or self.client
        clip = client.post(
            reverse("audio-clips"),
            {"file": SimpleUploadedFile("job.wav", make_wav(2), content_type="audio/wav"), "purpose": "job_description",
             "source": "recording"},
            format="multipart",
        ).json()
        transcription = client.post(reverse("audio-transcribe"), {"clip_id": clip["id"], "language": "ur"}, format="json").json()
        return clip, transcription

    def test_urdu_voice_request_keeps_the_original_and_asks_for_an_exact_time(self):
        clip, transcription = self.voice_source()
        created = self.client.post(reverse("jobs"), {"source_kind": "voice", "audio_clip_id": clip["id"], "source_language": "ur"},
                                   format="json")
        self.assertEqual(created.status_code, 201, created.content)
        job_id = created.json()["id"]
        interpretation = self.client.post(
            reverse("interpretations"),
            {"kind": "job_description", "transcription_id": transcription["id"], "language": "ur"}, format="json",
        ).json()
        body = self.client.post(reverse("job-source", args=[job_id]),
                                {"transcription_id": transcription["id"], "interpretation_id": interpretation["id"]},
                                format="json").json()
        original = body["source"]["original_text"]
        self.assertIn("کل شام", original)
        self.assertIn("نہیں چاہیے", original)  # the negated detail is preserved verbatim
        details = body["details"]
        self.assertEqual((details["trade"], details["services"], details["area"], details["city"]),
                         ("electrician", ["elec_fan_install"], "isb-g-9", "islamabad"))
        # "AC service not wanted" is another trade's service: it is not prefilled into this trade's lists.
        self.assertEqual(details["services_excluded"], [])
        self.assertEqual(details["preferred_time_text"], "کل شام")
        self.assertIsNone(details["window_start"])  # never guessed from "kal shaam"
        self.assertIn("preferred_time_text", body["suggestions"]["uncertain"])
        self.assertTrue(body["suggestions"]["simulated"])
        self.assertIn("window_start", body["issues"])
        # The customer corrects the description and chooses the actual window.
        fixed = self.patch(job_id, {"description": "دو پنکھے لگوانے ہیں۔", "window_start": karachi(1, 17),
                                    "window_end": karachi(1, 19)}).json()
        self.assertTrue(fixed["ready_to_confirm"])
        self.assertEqual(fixed["source"]["original_text"], original)
        self.assertEqual(self.confirm(job_id).json()["status"], "confirmed")

    def test_suggestions_only_fill_empty_fields(self):
        _, transcription = self.voice_source()
        job_id = self.client.post(reverse("jobs"), {"source_kind": "voice", "audio_clip_id": _["id"]}, format="json").json()["id"]
        self.patch(job_id, {"trade": "plumber", "services": ["plmb_leak_repair"]})
        interpretation = self.client.post(reverse("interpretations"), {"kind": "job_description",
                                          "transcription_id": transcription["id"], "language": "ur"}, format="json").json()
        body = self.client.post(reverse("job-source", args=[job_id]), {"interpretation_id": interpretation["id"]},
                                format="json").json()
        self.assertEqual((body["details"]["trade"], body["details"]["services"]), ("plumber", ["plmb_leak_repair"]))

    def test_draft_survives_a_provider_error(self):
        clip, _ = self.voice_source()
        job_id = self.client.post(reverse("jobs"), {"source_kind": "voice", "audio_clip_id": clip["id"]}, format="json").json()["id"]
        with mock.patch("apps.providers.interpretation.FixtureInterpretation.interpret", side_effect=ProviderUnavailable("timeout")):
            failed = self.client.post(reverse("interpretations"), {"kind": "job_description", "text": "AC theek karna hai",
                                      "language": "ur"}, format="json")
        self.assertEqual(failed.status_code, 502)
        reopened = self.client.get(reverse("job", args=[job_id])).json()
        self.assertEqual(reopened["status"], "draft")
        self.assertEqual(reopened["source"]["audio_clip_id"], clip["id"])
        # Manual path: the customer types the details without AI.
        self.assertEqual(self.patch(job_id, {**COMPLETE, "window_start": karachi(1, 9), "window_end": karachi(1, 10)}).status_code, 200)

    def test_another_customers_media_and_interpretations_cannot_be_attached(self):
        _, other = self.other()
        other_clip, other_transcription = self.voice_source(client=other)
        other_interp = other.post(reverse("interpretations"), {"kind": "job_description", "text": "پنکھا ٹھیک کرنا ہے",
                                  "language": "ur"}, format="json").json()
        response = self.client.post(reverse("jobs"), {"source_kind": "voice", "audio_clip_id": other_clip["id"]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("not_found", self.fields(response, "audio_clip_id"))
        job_id = self.create_text().json()["id"]
        for payload, name in (({"transcription_id": other_transcription["id"]}, "transcription_id"),
                              ({"interpretation_id": other_interp["id"]}, "interpretation_id")):
            with self.subTest(name=name):
                response = self.client.post(reverse("job-source", args=[job_id]), payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("not_found", self.fields(response, name))

    def test_interpretation_of_a_different_text_is_refused(self):
        job_id = self.create_text("Fix the geyser").json()["id"]
        other_text = self.client.post(reverse("interpretations"), {"kind": "job_description", "text": "پنکھا لگانا ہے",
                                      "language": "ur"}, format="json").json()
        response = self.client.post(reverse("job-source", args=[job_id]), {"interpretation_id": other_text["id"]}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "request_source_mismatch")


class AccessTests(JobApiTestCase):
    def test_other_customers_cannot_view_edit_confirm_or_download(self):
        job = self.create_text().json()
        photo = self.client.post(reverse("job-photos", args=[job["id"]]),
                                 {"image": SimpleUploadedFile("a.jpg", image_bytes(), content_type="image/jpeg")},
                                 format="multipart").json()
        _, other = self.other()
        self.assertEqual(other.get(reverse("job", args=[job["id"]])).status_code, 404)
        self.assertEqual(self.patch(job["id"], {"description": "x"}, client=other).status_code, 404)
        self.assertEqual(self.confirm(job["id"], client=other).status_code, 404)
        self.assertEqual(other.delete(reverse("job", args=[job["id"]])).status_code, 404)
        self.assertEqual(other.get(reverse("job-photo-content", args=[job["id"], photo["id"]])).status_code, 404)
        self.assertEqual(other.delete(reverse("job-photo", args=[job["id"], photo["id"]])).status_code, 404)
        self.assertEqual(other.get(reverse("jobs")).json()["count"], 0)

    def test_workers_cannot_browse_requests(self):
        job = self.create_text().json()
        _, worker = self.other("03003333333", role=User.Role.WORKER)
        self.assertEqual(worker.get(reverse("jobs")).status_code, 403)
        self.assertEqual(worker.get(reverse("job", args=[job["id"]])).status_code, 403)
        self.assertIn(APIClient().get(reverse("jobs")).status_code, (401, 403))

    def test_matching_summary_leaves_out_private_details(self):
        job = self.create_text().json()
        self.patch(job["id"], {**COMPLETE, "window_start": karachi(1, 9), "window_end": karachi(1, 11)})
        self.confirm(job["id"])
        summary = matching_summary(JobRequest.objects.get(pk=job["id"]))
        text = str(summary)
        self.assertNotIn("House 5", text)
        self.assertNotIn("Ring the bell", text)
        self.assertEqual(summary["area"], "isb-g-9")
        self.assertEqual(summary["budget_preference_pkr"], "3500.00")


class PhotoTests(JobApiTestCase):
    def setUp(self):
        super().setUp()
        self.job = self.create_text().json()["id"]

    def upload(self, data, name="p.jpg"):
        return self.client.post(reverse("job-photos", args=[self.job]),
                                {"image": SimpleUploadedFile(name, data, content_type="image/jpeg")}, format="multipart")

    def test_location_metadata_is_removed_and_content_is_private(self):
        original = image_bytes(gps=True)
        self.assertIn(b"Exif", original)
        response = self.upload(original)
        self.assertEqual(response.status_code, 201, response.content)
        photo = JobPhoto.objects.get()
        stored = photo.file.open("rb").read()
        self.assertNotIn(b"Exif", stored)
        self.assertEqual(len(Image.open(io.BytesIO(stored)).getexif()), 0)
        download = self.client.get(response.json()["content_url"])
        self.assertEqual(download.status_code, 200)
        self.assertIn("no-store", download["Cache-Control"])
        self.assertEqual(download["Content-Type"], "image/jpeg")

    def test_png_and_webp_are_accepted(self):
        self.assertEqual(self.upload(image_bytes("PNG"), "a.png").json()["mime_type"], "image/png")
        self.assertEqual(self.upload(image_bytes("WEBP"), "a.webp").json()["mime_type"], "image/webp")

    def test_unsupported_and_oversized_images(self):
        self.assertEqual(self.upload(b"%PDF-1.7" + b"x" * 500, "a.jpg").status_code, 415)
        self.assertEqual(self.upload(image_bytes()[:400]).status_code, 415)  # truncated JPEG
        gif = io.BytesIO()
        Image.new("RGB", (100, 100)).save(gif, format="GIF")
        self.assertEqual(self.upload(gif.getvalue(), "a.gif").status_code, 415)
        self.assertEqual(self.upload(image_bytes(size=(20, 20))).status_code, 400)
        with mock.patch("apps.jobs.photos.MAX_BYTES", 1000):
            self.assertEqual(self.upload(image_bytes()).status_code, 413)

    def test_at_most_five_photos_and_delete(self):
        for _ in range(5):
            self.assertEqual(self.upload(image_bytes()).status_code, 201)
        sixth = self.upload(image_bytes())
        self.assertEqual((sixth.status_code, sixth.json()["error"]["code"]), (409, "too_many_photos"))
        photo_id = self.client.get(reverse("job", args=[self.job])).json()["photos"][0]["id"]
        self.assertEqual(self.client.delete(reverse("job-photo", args=[self.job, photo_id])).status_code, 204)
        self.assertEqual(JobPhoto.objects.count(), 4)

    def test_photos_never_reach_ai_interpretation(self):
        with mock.patch("apps.providers.interpretation.FixtureInterpretation.interpret") as interpret:
            self.upload(image_bytes())
        interpret.assert_not_called()

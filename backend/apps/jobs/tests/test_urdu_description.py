"""English requests reach an Urdu-speaking worker (pitch item 4) and the deterministic matcher ranks them (item 6).

- Typed and spoken English keep the customer's own words as the description; the SAME interpretation call offers
  an Urdu description, which is shared only after the customer approves it for the current description.
- Changing the description makes a pending or approved Urdu version outdated (never shared as current).
- Without interpretation the request is still completed manually; the worker sees the original notes and their
  language, plus the localized structured details.
"""

import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.invitations.models import Invitation
from apps.invitations.tests.helpers import PASSWORD, User, client_for, make_worker, next_phone, seed
from apps.jobs.models import JobRequest
from apps.jobs.summary import matching_summary
from apps.providers.speech_to_text import TranscriptResult
from apps.voice.tests.helpers import make_wav
from apps.workers.models import WorkerProfile

from .test_jobs_api import karachi

ENGLISH = "Please install two ceiling fans in G-9 tomorrow evening. No AC service needed."


class UrduDescriptionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp(prefix="kaam-madad-urdu-")
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.user = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        self.client = client_for(self.user)

    # --- helpers -------------------------------------------------------------------------------------------

    def typed_english_job(self) -> dict:
        job = self.client.post(reverse("jobs"), {"source_kind": "text", "original_text": ENGLISH, "source_language": "en"},
                               format="json").json()
        interpretation = self.client.post(reverse("interpretations"), {"kind": "job_description", "text": ENGLISH,
                                                                       "language": "en"}, format="json")
        self.assertEqual(interpretation.status_code, 201, interpretation.content)
        attached = self.client.post(reverse("job-source", args=[job["id"]]), {"interpretation_id": interpretation.json()["id"]},
                                    format="json")
        self.assertEqual(attached.status_code, 200, attached.content)
        return attached.json()

    def finish_and_confirm(self, job_id: str, **extra) -> dict:
        body = {"city": "islamabad", "area": "isb-g-9", "window_start": karachi(1, 17), "window_end": karachi(1, 19), **extra}
        saved = self.client.patch(reverse("job", args=[job_id]), body, format="json")
        self.assertEqual(saved.status_code, 200, saved.content)
        confirmed = self.client.post(reverse("job-confirm", args=[job_id]))
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        return confirmed.json()

    def invite_and_open_as_worker(self, job_id: str) -> dict:
        profile = make_worker()
        sent = self.client.post(reverse("job-invitations", args=[job_id]), {"worker_id": str(profile.id)}, format="json")
        self.assertEqual(sent.status_code, 201, sent.content)
        return client_for(profile.user).get(reverse("invitation", args=[sent.json()["id"]])).json()

    # --- tests -------------------------------------------------------------------------------------------

    def test_typed_english_keeps_the_original_and_offers_urdu_for_review(self):
        job = self.typed_english_job()
        self.assertEqual(job["details"]["description"], ENGLISH)  # the customer's own words, not replaced
        self.assertEqual(job["source"]["original_text"], ENGLISH)
        urdu = job["urdu"]
        self.assertEqual((urdu["needed"], urdu["status"], urdu["description_language"]), (True, "suggested", "en"))
        self.assertIn("چھت کے پنکھے کی تنصیب", urdu["text"])
        self.assertEqual((job["details"]["trade"], job["details"]["services"]), ("electrician", ["elec_fan_install"]))
        self.assertEqual(job["details"]["services_excluded"], [])  # AC service is another trade: not a fan job option
        # A suggestion is never shared.
        self.finish_and_confirm(job["id"])
        self.assertIsNone(matching_summary(JobRequest.objects.get(pk=job["id"]))["description_ur"])

    def test_approved_urdu_reaches_the_urdu_worker_with_the_original_marked_english(self):
        job = self.typed_english_job()
        edited = job["urdu"]["text"] + " شام پانچ بجے کے بعد۔"
        self.finish_and_confirm(job["id"], description_ur=edited, description_ur_approved=True)
        invitation = self.invite_and_open_as_worker(job["id"])
        shared = invitation["job"]
        self.assertEqual((shared["description"], shared["description_language"], shared["description_ur"]), (ENGLISH, "en", edited))
        for private in ("address_private", "access_notes", "original_text", "audio_clip_id", "transcription_id"):
            self.assertNotIn(private, shared)

    def test_spoken_english_reaches_the_worker_with_the_approved_urdu(self):
        clip = self.client.post(reverse("audio-clips"), {"file": _wav_upload(), "purpose": "job_description", "source": "recording"},
                                format="multipart").json()
        job = self.client.post(reverse("jobs"), {"source_kind": "voice", "audio_clip_id": clip["id"], "source_language": "en"},
                               format="json").json()
        spoken = TranscriptResult(text=ENGLISH, language="en", no_speech=False, provider="elevenlabs", model="scribe_v3", simulated=False)
        with mock.patch("apps.providers.speech_to_text.FixtureSpeechToText.transcribe", return_value=spoken):
            transcription = self.client.post(reverse("audio-transcribe"), {"clip_id": clip["id"], "language": "en"}, format="json").json()
        self.client.post(reverse("job-source", args=[job["id"]]), {"transcription_id": transcription["id"]}, format="json")
        interpretation = self.client.post(reverse("interpretations"), {"kind": "job_description", "language": "en",
                                                                       "transcription_id": transcription["id"]}, format="json").json()
        job = self.client.post(reverse("job-source", args=[job["id"]]), {"interpretation_id": interpretation["id"]}, format="json").json()
        self.assertEqual(job["details"]["description"], ENGLISH)  # the transcript, not the Urdu wording
        self.assertEqual(job["urdu"]["status"], "suggested")
        self.finish_and_confirm(job["id"], description_ur_approved=True)
        shared = self.invite_and_open_as_worker(job["id"])["job"]
        self.assertTrue(shared["description_ur"])
        self.assertEqual(shared["description"], ENGLISH)

    def test_changing_the_description_makes_the_urdu_version_outdated(self):
        job = self.typed_english_job()
        approved = self.client.patch(reverse("job", args=[job["id"]]), {"description_ur_approved": True}, format="json").json()
        self.assertEqual(approved["urdu"]["status"], "approved")
        changed = self.client.patch(reverse("job", args=[job["id"]]), {"description": ENGLISH + " Three fans, not two."},
                                    format="json").json()
        self.assertEqual(changed["urdu"]["status"], "outdated")
        confirmed = self.finish_and_confirm(job["id"])
        self.assertIsNone(matching_summary(JobRequest.objects.get(pk=confirmed["id"]))["description_ur"])
        # After confirming: re-approving with the shared-description editor makes it current again.
        url = reverse("job-shared-description", args=[job["id"]])
        again = self.client.patch(url, {"description": changed["details"]["description"],
                                        "description_ur": "تین چھت کے پنکھے لگانے ہیں۔", "description_ur_approved": True},
                                  format="json")
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(matching_summary(JobRequest.objects.get(pk=job["id"]))["description_ur"], "تین چھت کے پنکھے لگانے ہیں۔")
        # Editing the description of a confirmed request makes it outdated again.
        edited = self.client.patch(url, {"description": "Three ceiling fans."}, format="json").json()
        self.assertEqual(edited["urdu"]["status"], "outdated")
        self.assertIsNone(matching_summary(JobRequest.objects.get(pk=job["id"]))["description_ur"])

    def test_approval_rules(self):
        job = self.typed_english_job()
        url = reverse("job", args=[job["id"]])
        latin = self.client.patch(url, {"description_ur": "Do pankhe", "description_ur_approved": True}, format="json")
        self.assertEqual(latin.status_code, 400)
        self.assertEqual(latin.json()["error"]["fields"]["description_ur"][0]["code"], "urdu_script_required")
        self.assertEqual(JobRequest.objects.get(pk=job["id"]).description_ur_status, "suggested")  # nothing saved
        edited = self.client.patch(url, {"description_ur_approved": True}, format="json").json()
        self.assertEqual(edited["urdu"]["status"], "approved")
        reedited = self.client.patch(url, {"description_ur": "دو پنکھے۔"}, format="json").json()
        self.assertEqual(reedited["urdu"]["status"], "suggested")  # an edit needs approval again

    @override_settings(INTERPRETATION_PROVIDER="unconfigured")
    def test_manual_request_without_interpretation_still_reaches_the_worker(self):
        job = self.client.post(reverse("jobs"), {"source_kind": "text", "original_text": ENGLISH, "source_language": "en"},
                               format="json").json()
        failed = self.client.post(reverse("interpretations"), {"kind": "job_description", "text": ENGLISH, "language": "en"},
                                  format="json")
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(failed.json()["error"]["code"], "ai_provider_not_configured")
        self.finish_and_confirm(job["id"], trade="electrician", services=["elec_fan_install"])
        shared = self.invite_and_open_as_worker(job["id"])["job"]
        self.assertEqual((shared["description"], shared["description_language"], shared["description_ur"]), (ENGLISH, "en", None))
        self.assertEqual((shared["trade"], shared["services"], shared["area"]), ("electrician", ["elec_fan_install"], "isb-g-9"))

    def test_urdu_requests_need_no_translation(self):
        job = self.client.post(reverse("jobs"), {"source_kind": "text", "original_text": "دو پنکھے لگوانے ہیں۔", "source_language": "ur"},
                               format="json").json()
        self.assertEqual((job["urdu"]["needed"], job["urdu"]["status"]), (False, "none"))


class AiSuggestedRequestRankingTests(TestCase):
    """The AI only suggests the request's catalog tags; the customer confirms them; the deterministic matcher ranks."""

    @classmethod
    def setUpTestData(cls):
        seed()
        call_command("seed_demo_workers", stdout=StringIO())

    def test_g9_ceiling_fan_request_ranks_the_fan_specialist_first_and_leaves_out_the_paused_worker(self):
        customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        client = client_for(customer)
        job = client.post(reverse("jobs"), {"source_kind": "text", "original_text": ENGLISH, "source_language": "en"}, format="json").json()
        interpretation = client.post(reverse("interpretations"), {"kind": "job_description", "text": ENGLISH, "language": "en"},
                                     format="json").json()
        job = client.post(reverse("job-source", args=[job["id"]]), {"interpretation_id": interpretation["id"]}, format="json").json()
        self.assertEqual((job["details"]["services"], job["details"]["area"]), (["elec_fan_install"], "isb-g-9"))
        client.patch(reverse("job", args=[job["id"]]), {"window_start": karachi(1, 17), "window_end": karachi(1, 19)}, format="json")
        self.assertEqual(client.post(reverse("job-confirm", args=[job["id"]])).status_code, 200)
        first = client.get(reverse("job-recommendations", args=[job["id"]])).json()
        again = client.get(reverse("job-recommendations", args=[job["id"]])).json()
        ids = [card["worker_id"] for card in first["workers"]]
        self.assertEqual(ids, [card["worker_id"] for card in again["workers"]])  # deterministic
        specialist = WorkerProfile.objects.get(user__phone_number="+923009990101")
        paused = WorkerProfile.objects.get(user__phone_number="+923009990104")
        self.assertEqual(ids[0], str(specialist.id))
        self.assertNotIn(str(paused.id), ids)
        self.assertFalse(Invitation.objects.exists())  # recommending never invites anyone


def _wav_upload():
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("clip.wav", make_wav(2), content_type="audio/wav")

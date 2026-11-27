import json
import shutil
import tempfile
import threading
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import httpx
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.conversations import quotes as rules
from apps.conversations.models import GapFinding, Message, Quote
from apps.conversations.views import submit_draft
from apps.core.api.exceptions import ApiError
from apps.invitations.models import Invitation
from apps.invitations.tests.helpers import KARACHI, PASSWORD, User, client_for, make_confirmed_job, make_worker, next_phone, seed
from apps.jobs.summary import matching_summary
from apps.providers.agreement import AgreementResult, GeminiAgreementChecker, verify_findings
from apps.voice.tests.helpers import make_wav

MATERIALS_INCLUDED = "دو پنکھے لگوانے ہیں۔ 1200 روپے سامان سمیت۔"


def tomorrow(hour: int):
    return (timezone.now() + timedelta(days=1)).astimezone(KARACHI).replace(hour=hour, minute=0, second=0, microsecond=0)


def quote_body(**overrides):
    body = {
        "inspection_only": False, "scope": "Install two ceiling fans", "quantity": 2, "labour_amount": "600",
        "labour_basis": "per_item", "materials": "customer", "materials_amount": None, "visit_fee": None,
        "visit_fee_treatment": "none", "exclusions": "Wiring changes",
        "start_at": tomorrow(17).isoformat(), "end_at": tomorrow(19).isoformat(),
    }
    body.update(overrides)
    return body


class ConversationTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp(prefix="kaam-madad-m7-")
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
        self.customer_user = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        self.customer = client_for(self.customer_user)
        self.job = make_confirmed_job(self.customer_user, description=MATERIALS_INCLUDED)
        self.profile = make_worker()
        self.worker = client_for(self.profile.user)
        self.invitation = Invitation.objects.create(job=self.job, worker_profile=self.profile, shared_summary=matching_summary(self.job))
        self.url = lambda name, *args: reverse(name, args=[self.invitation.id, *args])

    def send_text(self, client, text, client_id=None):
        return client.post(self.url("conversation-messages"), {"client_id": str(client_id or uuid.uuid4()), "kind": "text",
                                                               "text": text}, format="json")

    def save_draft(self, **overrides):
        return self.worker.put(self.url("conversation-quote-draft"), quote_body(**overrides), format="json")

    def submit(self):
        return self.worker.post(self.url("conversation-quote-submit"))

    def readiness(self):
        return self.customer.get(self.url("conversation-readiness")).json()

    def close(self, status):
        self.invitation.status, self.invitation.closed_at = status, timezone.now()
        self.invitation.save()


class MessagingTests(ConversationTestCase):
    def test_participants_exchange_text_and_a_third_account_cannot_read(self):
        self.assertEqual(self.send_text(self.customer, "السلام علیکم، کب آ سکتے ہیں؟").status_code, 201)
        self.assertEqual(self.send_text(self.worker, "کل شام پانچ بجے").status_code, 201)
        for client, role in ((self.customer, "customer"), (self.worker, "worker")):
            header = client.get(self.url("conversation")).json()
            self.assertEqual((header["role"], header["can_write"]), (role, True))
            texts = [m["text"] for m in client.get(self.url("conversation-messages")).json()["results"]]
            self.assertEqual(texts, ["السلام علیکم، کب آ سکتے ہیں؟", "کل شام پانچ بجے"])
        worker_header = self.worker.get(self.url("conversation")).json()
        self.assertEqual(worker_header["counterpart"], {"role": "customer"})  # no customer identity
        self.assertIsNone(worker_header["job_id"])  # the worker never gets the request ID
        self.assertEqual(self.customer.get(self.url("conversation")).json()["job_id"], str(self.job.id))
        self.assertNotIn("House 5", json.dumps(worker_header))
        strangers = [client_for(User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)),
                     client_for(make_worker().user)]
        for stranger in strangers:
            self.assertEqual(stranger.get(self.url("conversation")).status_code, 404)
            self.assertEqual(stranger.get(self.url("conversation-messages")).status_code, 404)
            self.assertEqual(self.send_text(stranger, "hi").status_code, 404)

    def test_voice_note_with_reviewed_caption_and_private_playback(self):
        clip = self.worker.post(reverse("audio-clips"), {"file": SimpleUploadedFile("note.wav", make_wav(2), content_type="audio/wav"),
                                                         "purpose": "message", "source": "recording"}, format="multipart").json()
        transcription = self.worker.post(reverse("audio-transcribe"), {"clip_id": clip["id"], "language": "ur"}, format="json").json()
        self.assertIn("سامان", transcription["text"])
        # The draft upload stays owner-only before it is sent.
        self.assertEqual(self.customer.get(f"/api/v1/audio/clips/{clip['id']}/content/").status_code, 404)
        edited = "میں کل شام پانچ بجے آؤں گا۔ پنکھوں کا سامان آپ لے کر رکھیں۔"
        sent = self.worker.post(self.url("conversation-messages"), {
            "client_id": str(uuid.uuid4()), "kind": "voice", "audio_clip_id": clip["id"],
            "transcription_id": transcription["id"], "text": edited}, format="json")
        self.assertEqual(sent.status_code, 201, sent.content)
        mine = sent.json()
        self.assertEqual((mine["caption_status"], mine["text"]), ("approved", edited))
        self.assertEqual(mine["interpreted_text"], transcription["text"])  # stored separately
        theirs = self.customer.get(self.url("conversation-messages")).json()["results"][0]
        self.assertEqual(theirs["text"], edited)
        self.assertIsNone(theirs["interpreted_text"])
        for client in (self.customer, self.worker):
            audio = client.get(theirs["audio_url"])
            self.assertEqual(audio.status_code, 200)
            self.assertIn("no-store", audio["Cache-Control"])
        stranger = client_for(User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER))
        self.assertEqual(stranger.get(theirs["audio_url"]).status_code, 404)
        # The same clip cannot be attached twice; job-description clips cannot become voice notes.
        again = self.worker.post(self.url("conversation-messages"), {"client_id": str(uuid.uuid4()), "kind": "voice",
                                                                     "audio_clip_id": clip["id"]}, format="json")
        self.assertEqual(again.status_code, 400)

    def test_caption_unavailable_and_typed_caption(self):
        def clip():
            return self.customer.post(reverse("audio-clips"), {"file": SimpleUploadedFile("n.wav", make_wav(1), content_type="audio/wav"),
                                                               "purpose": "message"}, format="multipart").json()["id"]
        no_caption = self.customer.post(self.url("conversation-messages"), {"client_id": str(uuid.uuid4()), "kind": "voice",
                                                                            "audio_clip_id": clip()}, format="json").json()
        self.assertEqual((no_caption["caption_status"], no_caption["text"]), ("unavailable", ""))
        typed = self.customer.post(self.url("conversation-messages"), {"client_id": str(uuid.uuid4()), "kind": "voice",
                                                                       "audio_clip_id": clip(), "text": "دو پنکھے"}, format="json").json()
        self.assertEqual(typed["caption_status"], "typed")

    def test_retry_with_the_same_client_id_gives_one_message(self):
        client_id = uuid.uuid4()
        first = self.send_text(self.customer, "Hello", client_id)
        second = self.send_text(self.customer, "Hello", client_id)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(Message.objects.count(), 1)

    def test_pagination_and_polling(self):
        for n in range(35):
            Message.objects.create(invitation=self.invitation, sender=self.customer_user, sender_role="customer",
                                   client_id=uuid.uuid4(), kind="text", text=f"m{n}",
                                   created_at=timezone.now() - timedelta(minutes=100 - n))
        latest = self.customer.get(self.url("conversation-messages")).json()
        self.assertEqual(len(latest["results"]), 30)
        self.assertTrue(latest["has_more_before"])
        self.assertEqual(latest["results"][-1]["text"], "m34")
        older = self.customer.get(self.url("conversation-messages"), {"before": latest["results"][0]["id"]}).json()
        self.assertEqual([m["text"] for m in older["results"]], [f"m{n}" for n in range(5)])
        self.assertFalse(older["has_more_before"])
        self.send_text(self.worker, "new")
        polled = self.customer.get(self.url("conversation-messages"), {"after": latest["results"][-1]["id"]}).json()
        self.assertEqual([m["text"] for m in polled["results"]], ["new"])

    def test_closed_invitation_keeps_history_but_blocks_writes(self):
        self.send_text(self.customer, "Before closing")
        self.save_draft()
        for status in ("withdrawn", "declined"):
            with self.subTest(status=status):
                self.close(status)
                for client in (self.customer, self.worker):
                    self.assertEqual(client.get(self.url("conversation-messages")).json()["results"][0]["text"], "Before closing")
                    self.assertFalse(client.get(self.url("conversation")).json()["can_write"])
                blocked = self.send_text(self.worker, "After closing")
                self.assertEqual((blocked.status_code, blocked.json()["error"]["code"]), (409, "conversation_closed"))
                self.assertEqual(self.save_draft().status_code, 409)
                self.assertEqual(self.submit().status_code, 409)
                self.assertIn("invitation_not_active", self.readiness()["blocking"])


class QuoteTests(ConversationTestCase):
    def test_materials_conflict_clarified_by_a_revised_quote(self):
        self.assertEqual(self.save_draft().status_code, 200)
        v1 = self.submit()
        self.assertEqual(v1.status_code, 201, v1.content)
        v1 = v1.json()
        self.assertEqual((v1["version"], v1["status"], v1["check"]["status"]), (1, "submitted", "findings"))
        self.assertTrue(v1["check"]["simulated"])
        self.assertEqual(v1["totals"], {"labour_total": "1200.00", "materials_total": "0.00", "visit_total": "0.00",
                                        "known_total": "1200.00", "unknown": [], "complete": True})
        finding = next(f for f in v1["findings"] if f["code"] == "materials_responsibility")
        self.assertEqual(finding["ask"], "worker")
        self.assertIn("سامان کون لائے گا", finding["question"])  # same language as the quoted statement
        self.assertIn({"kind": "request", "ref": "description", "text": "1200 روپے سامان سمیت۔"}, finding["sources"])
        self.assertIn({"kind": "quote", "ref": "materials", "text": "customer"}, finding["sources"])
        self.assertEqual(self.readiness()["blocking"], ["unresolved_findings"])

        # Clarification in the chat, then a revised quote with materials included.
        self.send_text(self.worker, "ٹھیک ہے، سامان میں لاؤں گا۔ کل 1500 روپے۔")
        self.save_draft(labour_basis="total", quantity=2, labour_amount="1500", materials="included")
        v2 = self.submit().json()
        self.assertEqual((v2["version"], v2["check"]["status"], v2["findings"]), (2, "passed", []))
        listing = self.customer.get(self.url("conversation-quotes")).json()
        self.assertEqual(listing["current"]["version"], 2)
        self.assertEqual([q["version"] for q in listing["history"]], [1])
        self.assertEqual(listing["history"][0]["labour_amount"], "600.00")  # the old version is preserved
        self.assertEqual(listing["history"][0]["findings"][0]["code"], "materials_responsibility")
        ready = self.readiness()
        self.assertTrue(ready["ready"], ready)
        self.assertEqual((ready["version"], ready["quote_id"], ready["invitation_id"]), (2, v2["id"], str(self.invitation.id)))
        self.assertEqual(ready["expires_at"], v2["expires_at"])  # same "…Z" UTC format as every other timestamp
        self.assertTrue(ready["expires_at"].endswith("Z"))
        old = self.customer.get(self.url("conversation-quote", v1["id"])).json()["readiness"]
        self.assertIn("quote_superseded", old["blocking"])

    def test_explicit_resolution_of_a_false_positive(self):
        self.save_draft()
        quote = self.submit().json()
        finding = quote["findings"][0]
        empty = self.customer.post(self.url("conversation-finding-resolve", quote["id"], finding["id"]),
                                   {"resolution": "not_a_conflict", "note": ""}, format="json")
        self.assertEqual(empty.status_code, 400)  # never dismissed without explicit terms
        resolved = self.customer.post(self.url("conversation-finding-resolve", quote["id"], finding["id"]),
                                      {"resolution": "not_a_conflict", "note": "میں سامان خود خریدوں گا۔ صرف لیبر 1200۔"},
                                      format="json").json()
        stored = resolved["findings"][0]
        self.assertEqual((stored["status"], stored["resolved_role"]), ("resolved", "customer"))
        self.assertTrue(resolved["readiness"]["ready"])

    def test_deterministic_validation_and_totals(self):
        cases = [
            ({"labour_amount": None}, "labour_amount", "required"),
            ({"quantity": None}, "quantity", "required"),
            ({"materials": ""}, "materials", "required"),
            ({"materials_amount": "300"}, "materials_amount", "materials_amount_not_applicable"),
            ({"visit_fee": "200"}, "visit_fee_treatment", "visit_fee_treatment_missing"),
            ({"visit_fee_treatment": "charged"}, "visit_fee", "required"),
            ({"start_at": tomorrow(19).isoformat(), "end_at": tomorrow(17).isoformat()}, "end_at", "window_end_before_start"),
            ({"start_at": (timezone.now() - timedelta(hours=2)).isoformat(), "end_at": timezone.now().isoformat()}, "start_at", "window_in_past"),
            ({"scope": ""}, "scope", "required"),
            ({"quantity": 0}, "quantity", "quantity_out_of_range"),
            ({"quantity": 1000}, "quantity", "quantity_out_of_range"),
        ]
        for overrides, field, code in cases:
            with self.subTest(code=code, field=field):
                draft = self.save_draft(**overrides).json()
                self.assertIn(code, draft["issues"].get(field, []))
                response = self.submit()
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(code, [e["code"] for e in response.json()["error"]["fields"][field]])
        self.assertFalse(Quote.objects.exclude(status="draft").exists())

        extra = self.save_draft(materials="worker_extra", materials_amount=None, visit_fee="300",
                                visit_fee_treatment="charged").json()["totals"]
        self.assertEqual((extra["known_total"], extra["unknown"], extra["complete"]), ("1500.00", ["materials"], False))

    def test_inspection_only_quote(self):
        self.save_draft(inspection_only=True, labour_amount=None, materials="", visit_fee="500",
                        visit_fee_treatment="waived_if_hired", scope="Find out why the fan is not working")
        quote = self.submit().json()
        self.assertEqual(quote["status"], "submitted", quote)
        self.assertEqual((quote["totals"]["known_total"], quote["totals"]["unknown"]), ("500.00", ["repair"]))
        self.assertIn("unknown_amounts", self.readiness()["warnings"])
        self.save_draft(inspection_only=True, labour_amount=None, materials="", visit_fee=None, visit_fee_treatment="none")
        bad = self.submit()
        self.assertEqual(bad.status_code, 400)

    def test_expiry_is_24_hours_or_the_start_time(self):
        self.save_draft(materials="included", labour_basis="total", labour_amount="1200")
        quote = Quote.objects.get(pk=self.submit().json()["id"])
        self.assertEqual(quote.expires_at, min(quote.submitted_at + timedelta(hours=24), quote.start_at))
        with mock.patch("django.utils.timezone.now", return_value=quote.expires_at + timedelta(seconds=1)):
            blocking = self.readiness()["blocking"]
        self.assertIn("quote_expired", blocking)

    def test_time_outside_the_request_needs_the_customer(self):
        self.save_draft(materials="included", labour_basis="total", labour_amount="1200",
                        start_at=tomorrow(9).isoformat(), end_at=tomorrow(11).isoformat())
        quote = self.submit().json()
        timing = next(f for f in quote["findings"] if f["code"] == "timing_differs")
        self.assertEqual((timing["source"], timing["ask"], timing["blocking"]), ("rule", "customer", True))
        self.assertIn("unresolved_findings", self.readiness()["blocking"])

    def test_unexpected_checker_error_is_recorded_as_unavailable(self):
        self.save_draft(materials="included", labour_basis="total", labour_amount="1200")
        with mock.patch("apps.providers.agreement.FixtureAgreementChecker.check", side_effect=RuntimeError("boom")):
            quote = self.submit()
        self.assertEqual(quote.status_code, 201)
        self.assertEqual(quote.json()["check"]["status"], "unavailable")
        self.assertIn("automated_check_unavailable", self.readiness()["blocking"])

    @override_settings(AGREEMENT_CHECK_PROVIDER="unconfigured")
    def test_ai_failure_is_never_a_pass_and_manual_review_is_explicit(self):
        self.save_draft(materials="included", labour_basis="total", labour_amount="1200")
        quote = self.submit().json()
        self.assertEqual((quote["check"]["status"], quote["check"]["failure"]), ("unavailable", "ai_provider_not_configured"))
        self.assertEqual(self.readiness()["blocking"], ["automated_check_unavailable"])
        self.assertEqual(self.worker.post(self.url("conversation-quote-manual-review", quote["id"])).status_code, 403)
        reviewed = self.customer.post(self.url("conversation-quote-manual-review", quote["id"])).json()
        self.assertEqual(reviewed["check"]["status"], "unavailable")  # still shown as not run, not as passed
        self.assertTrue(reviewed["readiness"]["ready"])

    def test_retry_check_after_failure(self):
        with override_settings(AGREEMENT_CHECK_PROVIDER="unconfigured"):
            self.save_draft()
            quote = self.submit().json()
        rerun = self.worker.post(self.url("conversation-quote-check", quote["id"])).json()
        self.assertEqual(rerun["check"]["status"], "findings")
        self.assertEqual(self.worker.post(self.url("conversation-quote-check", quote["id"])).status_code, 409)

    def test_roles_and_privacy(self):
        self.assertEqual(self.customer.put(self.url("conversation-quote-draft"), quote_body(), format="json").status_code, 403)
        self.save_draft()
        self.assertIsNone(self.customer.get(self.url("conversation-quotes")).json()["draft"])  # drafts are the worker's
        self.assertIsNotNone(self.worker.get(self.url("conversation-quotes")).json()["draft"])
        result = AgreementResult(findings=[], provider="fixture", model="x", simulated=True)
        with mock.patch("apps.providers.agreement.FixtureAgreementChecker.check", return_value=result) as check:
            self.submit()
        sent = json.dumps(check.call_args.kwargs, ensure_ascii=False)
        self.assertIn("Install two ceiling fans", sent)
        # Request window and quote times reach the checker in one Asia/Karachi format (equal instants look equal).
        kwargs = check.call_args.kwargs
        for value in (kwargs["request"]["window_start"], kwargs["request"]["window_end"], kwargs["quote"]["start_at"], kwargs["quote"]["end_at"]):
            self.assertTrue(value.endswith("+05:00"), value)
        for private in ("House 5", "Ring twice", "secret original", self.customer_user.phone_number):
            self.assertNotIn(private, sent)


class AgreementProviderTests(SimpleTestCase):
    REQUEST = {"description": "Two fans, 1200 including materials", "trade": "electrician", "services": [], "services_excluded": [],
               "area": "isb-g-9", "window_start": "x", "window_end": "y", "budget_preference_pkr": None}
    MESSAGES = [{"id": "m1", "role": "worker", "text": "Labour only, you buy the fans."}]
    QUOTE = {"materials": "customer", "labour_amount_pkr": "1200.00"}

    def test_invented_sources_are_dropped(self):
        raw = [
            {"code": "materials_responsibility", "ask": "worker", "question": "Who supplies materials?",
             "sources": [{"kind": "request", "ref": "description", "text": "including materials"},
                         {"kind": "message", "ref": "m1", "text": "I will bring everything"}]},
            {"code": "scope_mismatch", "ask": "both", "question": "?", "sources": [{"kind": "message", "ref": "m9", "text": "x"}]},
            {"code": "made_up", "ask": "worker", "question": "?", "sources": []},
        ]
        verified = verify_findings(raw, self.REQUEST, self.MESSAGES, self.QUOTE)
        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["sources"], [{"kind": "request", "ref": "description", "text": "including materials"}])

    @override_settings(GEMINI_API_KEY="k", GEMINI_AGREEMENT_MODEL="gemini-3.6-flash", AI_PROVIDER_MAX_RETRIES=0)
    def test_gemini_request_shape(self):
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.content)
            text = json.dumps({"findings": [{"code": "materials_responsibility", "ask": "worker", "question": "Who supplies?",
                                             "sources": [{"kind": "message", "ref": "m1", "text": "you buy the fans"}]}]})
            return httpx.Response(200, json={"steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}]})

        result = GeminiAgreementChecker(client=httpx.Client(transport=httpx.MockTransport(handler))).check(
            request=self.REQUEST, messages=self.MESSAGES, quote=self.QUOTE)
        self.assertFalse(seen["body"]["store"])
        self.assertIn("including materials", seen["body"]["input"][0]["text"])
        self.assertEqual((result.provider, result.simulated, len(result.findings)), ("gemini", False, 1))


class ConcurrencyTests(TransactionTestCase):
    """Real concurrent transactions on PostgreSQL: quote submission vs invitation closure."""

    def setUp(self):
        seed()
        self.customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        self.job = make_confirmed_job(self.customer)
        self.profile = make_worker()

    def _invitation_with_draft(self):
        invitation = Invitation.objects.create(job=self.job, worker_profile=self.profile, shared_summary=matching_summary(self.job))
        Quote.objects.create(invitation=invitation, scope="Two fans", quantity=2, labour_amount=Decimal("600"),
                             labour_basis="per_item", materials="included", start_at=tomorrow(17), end_at=tomorrow(19))
        return invitation

    def _race(self, *actions):
        barrier = threading.Barrier(len(actions))
        outcomes = []

        def run(action):
            try:
                barrier.wait()
                outcomes.append(action())
            except ApiError as exc:
                outcomes.append(exc.default_code if not exc.get_codes() else exc.get_codes())
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(a,)) for a in actions]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        return outcomes

    def _withdraw(self, invitation_id):
        from django.db import transaction

        with transaction.atomic():
            invitation = Invitation.objects.select_for_update().get(pk=invitation_id)
            if invitation.status == Invitation.Status.ACTIVE:
                invitation.status, invitation.closed_at = Invitation.Status.WITHDRAWN, timezone.now()
                invitation.save()
        return "withdrawn"

    def test_submit_and_withdraw_race_never_leaves_a_quote_submitted_after_closure(self):
        for _ in range(5):
            invitation = self._invitation_with_draft()
            self._race(lambda: submit_draft(invitation.id, self.profile.user), lambda: self._withdraw(invitation.id))
            invitation.refresh_from_db()
            self.assertEqual(invitation.status, "withdrawn")
            for quote in invitation.quotes.exclude(status="draft"):
                self.assertLessEqual(quote.submitted_at, invitation.closed_at)
            self.assertFalse(rules.readiness(invitation)["ready"])
            Quote.objects.filter(invitation=invitation).delete()
            Invitation.objects.filter(pk=invitation.pk).delete()

    def test_double_submit_creates_one_version(self):
        invitation = self._invitation_with_draft()
        outcomes = self._race(lambda: submit_draft(invitation.id, self.profile.user),
                              lambda: submit_draft(invitation.id, self.profile.user))
        self.assertEqual(Quote.objects.filter(invitation=invitation, status="submitted").count(), 1)
        self.assertEqual(Quote.objects.filter(invitation=invitation).count(), 1)
        self.assertEqual(sum(1 for o in outcomes if isinstance(o, Quote)), 1)
        self.assertEqual(GapFinding.objects.count(), 0)  # included materials + window inside the request: no rule findings

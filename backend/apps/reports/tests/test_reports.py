import io
import shutil
import tempfile
import uuid
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import PermissionDenied

from apps.bookings import services as bookings
from apps.bookings.models import Booking
from apps.bookings.tests.test_bookings import accept_body, at, make_invitation, ready_quote
from apps.invitations.models import Invitation
from apps.invitations.tests.helpers import PASSWORD, User, client_for, make_worker, next_phone, seed
from apps.reports import services
from apps.reports.models import ContactBlock, EvidenceAccess, Report, ReportDecision, ReportEvidence
from apps.reviews.tests.test_completion import staff_with, started
from apps.voice.models import AudioClip
from apps.voice.tests.helpers import make_wav


def png(size=(120, 90)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class ReportTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp(prefix="kaam-madad-m10-")
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
        self.profile = make_worker()
        self.worker = client_for(self.profile.user)
        self.invitation = make_invitation(self.customer_user, self.profile)

    def file(self, client, *, key=None, **body):
        payload = {"client_id": str(key or uuid.uuid4()), "category": "harassment", "description": "اس نے بار بار نامناسب پیغامات بھیجے"}
        payload.update(body)
        if "invitation_id" not in payload and "booking_id" not in payload:
            payload["invitation_id"] = str(self.invitation.id)
        return client.post(reverse("reports"), payload, format="json")

    def report_clip(self, client):
        return client.post(reverse("audio-clips"), {"file": SimpleUploadedFile("r.wav", make_wav(2), content_type="audio/wav"),
                                                     "purpose": "report", "source": "recording"}, format="multipart").json()

    def message(self, client, text="hello"):
        return client.post(reverse("conversation-messages", args=[self.invitation.id]),
                           {"client_id": str(uuid.uuid4()), "kind": "text", "text": text}, format="json")


class FilingTests(ReportTestCase):
    def test_either_role_can_report_the_other_participant_and_retries_are_safe(self):
        key = uuid.uuid4()
        first = self.file(self.customer, key=key)
        self.assertEqual(first.status_code, 201, first.content)
        report = Report.objects.get(pk=first.json()["id"])
        self.assertEqual((report.reported_id, report.reporter_role, first.json()["status"]), (self.profile.user_id, "customer", "open"))
        self.assertEqual(self.file(self.customer, key=key).status_code, 200)  # a retry: same report
        self.assertEqual(Report.objects.count(), 1)

        clip = self.report_clip(self.worker)
        by_worker = self.file(self.worker, description="", audio_clip_id=clip["id"], category="threats")
        self.assertEqual(by_worker.status_code, 201, by_worker.content)
        self.assertEqual(Report.objects.get(pk=by_worker.json()["id"]).reported_id, self.customer_user.pk)
        self.assertEqual(by_worker.json()["evidence"][0]["role"], "statement")  # a voice note is enough

    def test_the_reported_person_comes_from_the_interaction_only(self):
        self.assertEqual(self.file(self.customer, reported_id=str(self.customer_user.pk)).json()["error"]["fields"]["reported_id"][0]["code"],
                         "unexpected_field")
        stranger = client_for(User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER))
        self.assertEqual(self.file(stranger).status_code, 404)  # not a participant
        empty = self.file(self.customer, description="  ")
        self.assertEqual(empty.json()["error"]["fields"]["description"][0]["code"], "required")
        both = self.file(self.customer, invitation_id=str(self.invitation.id), booking_id=str(uuid.uuid4()))
        self.assertEqual(both.status_code, 400)

    def test_reports_work_after_the_interaction_closed_and_change_nothing_in_a_booking(self):
        self.invitation.status, self.invitation.closed_at = "withdrawn", timezone.now()
        self.invitation.save()
        self.assertEqual(self.file(self.worker, category="no_show").status_code, 201)

        other_customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        booking = started(other_customer, self.profile, at(2, 10))
        events = booking.events.count()
        response = client_for(other_customer).post(reverse("reports"), {"client_id": str(uuid.uuid4()), "booking_id": str(booking.pk),
                                                                         "category": "property_work", "description": "دیوار پر نشان"}, format="json")
        self.assertEqual(response.status_code, 201)
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.events.count()), ("in_progress", events))  # untouched
        self.assertEqual(bookings.request_completion(self.profile.user, booking.pk).status, "completion_requested")  # M9 flow intact

    def test_report_audio_is_never_transcribed(self):
        clip = self.report_clip(self.customer)
        response = self.customer.post(reverse("audio-transcribe"), {"clip_id": clip["id"], "language": "ur"}, format="json")
        self.assertEqual(response.json()["error"]["fields"]["clip_id"][0]["code"], "not_transcribable")


class PrivacyTests(ReportTestCase):
    def test_only_the_reporter_can_read_the_report_and_download_evidence(self):
        report = self.file(self.customer).json()
        evidence = self.customer.post(reverse("report-evidence", args=[report["id"]]),
                                      {"file": SimpleUploadedFile("e.png", png(), content_type="image/png")}, format="multipart")
        self.assertEqual(evidence.status_code, 201, evidence.content)
        item = evidence.json()["evidence"][0]
        url = reverse("report-evidence-content", args=[report["id"], item["id"]])
        self.assertEqual(self.customer.get(url).status_code, 200)
        stranger = client_for(User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER))
        for client in (self.worker, stranger):  # the reported person and a third account
            self.assertEqual(client.get(reverse("report", args=[report["id"]])).status_code, 404)
            self.assertEqual(client.get(url).status_code, 404)
            self.assertEqual(client.get(reverse("reports")).json()["count"], 0)
            self.assertEqual(client.post(reverse("report-replies", args=[report["id"]]), {"text": "x y"}, format="json").status_code, 404)
        stored = ReportEvidence.objects.get(pk=item["id"])
        self.assertEqual(stored.mime_type, "image/png")  # re-encoded by the photo pipeline (metadata removed)
        # The reported worker's own screens say nothing about the report.
        self.assertNotIn(report["id"], str(self.worker.get(reverse("conversation", args=[self.invitation.id])).content))

    def test_report_text_is_not_logged(self):
        with self.assertLogs("apps.reports", level="INFO") as logs:
            self.file(self.customer, description="بہت خاص خفیہ جملہ")
        self.assertNotIn("خفیہ", "\n".join(logs.output))

    def test_evidence_limits(self):
        report = self.file(self.customer).json()
        url = reverse("report-evidence", args=[report["id"]])
        bad = self.customer.post(url, {"file": SimpleUploadedFile("x.png", b"not an image at all" * 10, content_type="image/png")}, format="multipart")
        self.assertEqual(bad.status_code, 415)  # content checked, not the declared type
        for _ in range(5):
            self.assertEqual(self.customer.post(url, {"file": SimpleUploadedFile("e.png", png(), content_type="image/png")},
                                                format="multipart").status_code, 201)
        sixth = self.customer.post(url, {"file": SimpleUploadedFile("e.png", png(), content_type="image/png")}, format="multipart")
        self.assertEqual(sixth.json()["error"]["code"], "too_much_evidence")
        clip = self.report_clip(self.worker)  # someone else's recording
        self.assertEqual(self.customer.post(url, {"audio_clip_id": clip["id"]}, format="json").status_code, 409)


class StaffTests(ReportTestCase):
    def test_request_information_reply_and_resolve_with_an_audit_trail(self):
        report_id = self.file(self.customer).json()["id"]
        with self.assertRaises(PermissionDenied):
            services.decide(staff_with(), report_id, action="mark_reviewing", reason="Looking")
        staff = staff_with("review_report")
        with self.assertRaises(Exception):
            services.decide(staff, report_id, action="request_info", reason="Need dates")  # message to reporter required
        services.decide(staff, report_id, action="request_info", reason="Need dates", message_to_reporter="کب ہوا؟ تاریخ بتائیں۔",
                        internal_note="Worker has no earlier reports.")
        view = self.customer.get(reverse("report", args=[report_id])).json()
        self.assertEqual((view["status"], view["awaiting_reply"]), ("reviewing", True))
        self.assertEqual(view["messages"], [{"from": "staff", "text": "کب ہوا؟ تاریخ بتائیں۔", "at": view["messages"][0]["at"]}])
        self.assertNotIn("earlier reports", str(view))  # internal notes never reach the reporter
        reply = self.customer.post(reverse("report-replies", args=[report_id]), {"text": "پچھلے منگل کو"}, format="json").json()
        self.assertEqual((reply["awaiting_reply"], reply["messages"][-1]["from"]), (False, "you"))
        services.decide(staff, report_id, action="resolve", reason="Warned the worker", message_to_reporter="ہم نے کارروائی کر لی ہے۔")
        closed = self.customer.get(reverse("report", args=[report_id])).json()
        self.assertEqual((closed["status"], closed["can_reply"]), ("resolved", False))
        self.assertEqual(self.customer.post(reverse("report-replies", args=[report_id]), {"text": "ok ok"}, format="json").status_code, 409)
        decisions = list(ReportDecision.objects.filter(report_id=report_id).values_list("action", "old_state", "new_state"))
        self.assertEqual(decisions[0], ("request_info", {"status": "open", "awaiting_reply": False}, {"status": "reviewing", "awaiting_reply": True}))
        self.assertEqual(decisions[-1][0], "resolve")
        self.assertTrue(all(d.actor_id == staff.pk for d in ReportDecision.objects.filter(report_id=report_id)))

    def test_admin_queue_decision_and_evidence_permissions(self):
        report_id = self.file(self.customer).json()["id"]
        self.customer.post(reverse("report-evidence", args=[report_id]), {"file": SimpleUploadedFile("e.png", png(), content_type="image/png")},
                           format="multipart")
        evidence_id = ReportEvidence.objects.get().pk
        queue, decide = reverse("admin:reports_report_changelist"), reverse("admin:reports_report_decide", args=[report_id])
        evidence = reverse("admin:reports_report_evidence", args=[report_id, evidence_id])
        self.client.force_login(staff_with())
        self.assertEqual(self.client.get(queue).status_code, 403)
        self.assertEqual(self.client.get(decide).status_code, 403)
        reviewer = staff_with("review_report")
        self.client.force_login(reviewer)
        self.assertEqual(self.client.get(queue, {"status__exact": "open", "category__exact": "harassment"}).status_code, 200)
        self.assertEqual(self.client.get(evidence).status_code, 403)  # reviewing does not include evidence
        self.assertFalse(EvidenceAccess.objects.exists())
        response = self.client.post(decide, {"action": "mark_reviewing", "reason": "Taking this case"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Report.objects.get(pk=report_id).status, "reviewing")
        self.client.force_login(staff_with("review_report", "view_evidence"))
        self.assertEqual(self.client.get(evidence).status_code, 200)
        self.assertEqual(EvidenceAccess.objects.count(), 1)  # the opening is recorded

    def test_account_actions_need_their_own_permission_and_keep_the_report(self):
        report_id = self.file(self.customer).json()["id"]
        reviewer = staff_with("review_report")
        with self.assertRaises(PermissionDenied):
            services.decide(reviewer, report_id, action="note", reason="Pattern", account_action="restrict", account_reason="Harassment")
        moderator = staff_with("review_report", "take_account_action")
        services.decide(moderator, report_id, action="note", reason="Pattern of messages", account_action="restrict",
                        account_reason="Harassment confirmed by staff")
        worker_user = User.objects.get(pk=self.profile.user_id)
        self.assertIsNotNone(worker_user.restricted_at)
        audit = ReportDecision.objects.get(report_id=report_id, action="restrict")
        self.assertEqual((audit.old_state, audit.new_state), ({"is_active": True, "restricted": False}, {"is_active": True, "restricted": True}))
        self.assertEqual(Report.objects.get(pk=report_id).description, "اس نے بار بار نامناسب پیغامات بھیجے")
        services.decide(moderator, report_id, action="note", reason="Appeal accepted", account_action="lift_restriction", account_reason="Appeal")
        self.assertIsNone(User.objects.get(pk=self.profile.user_id).restricted_at)
        services.decide(moderator, report_id, action="note", reason="Threats", account_action="suspend", account_reason="Threats")
        self.assertFalse(self.worker.get(reverse("auth-me")).json()["authenticated"])  # suspension: the session no longer authenticates
        self.assertEqual(self.message(self.worker).status_code, 401)  # signed out


class RestrictionTests(ReportTestCase):
    def restrict(self, user):
        User.objects.filter(pk=user.pk).update(restricted_at=timezone.now())

    def test_a_restricted_worker_keeps_existing_records_but_starts_nothing_new(self):
        other_customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        booking = started(other_customer, self.profile, at(2, 10))
        report = self.file(self.customer).json()
        services.decide(staff_with("review_report"), report["id"], action="request_info", reason="More", message_to_reporter="?")
        self.restrict(self.profile.user)
        self.assertEqual(self.message(self.worker).json()["error"]["code"], "account_restricted")
        header = self.worker.get(reverse("conversation", args=[self.invitation.id])).json()
        self.assertEqual((header["can_write"], header["write_blocked_reason"]), (False, "account_restricted"))
        self.assertEqual(self.worker.get(reverse("conversation-messages", args=[self.invitation.id])).status_code, 200)
        self.assertEqual(self.file(self.worker, category="other", description="وہ گالیاں دیتے ہیں").status_code, 201)  # can still report
        # Not recommended, cannot be invited, cannot be booked from an existing quote.
        new_customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        fresh = make_invitation(new_customer, make_worker())
        job_id = fresh.job_id
        ids = [w["worker_id"] for w in client_for(new_customer).get(reverse("job-recommendations", args=[job_id])).json()["workers"]]
        self.assertNotIn(str(self.profile.id), ids)
        quote = ready_quote(make_invitation(new_customer, self.profile), start=at(4, 10))
        refused = client_for(new_customer).post(reverse("bookings"), accept_body(quote), format="json").json()["error"]
        self.assertEqual(refused["code"], "worker_not_eligible")
        # The existing booking and its M9 completion flow are untouched.
        self.assertEqual(bookings.request_completion(self.profile.user, booking.pk).status, "completion_requested")
        self.assertEqual(bookings.confirm_completion(other_customer, booking.pk).status, "completed")

    def test_a_restricted_customer_cannot_open_requests_invite_or_book_but_can_report_and_reply(self):
        report = self.file(self.customer).json()
        services.decide(staff_with("review_report"), report["id"], action="request_info", reason="More", message_to_reporter="?")
        quote = ready_quote(self.invitation)
        self.restrict(self.customer_user)
        self.assertEqual(self.customer.post(reverse("jobs"), {"source_kind": "text", "original_text": "نیا کام"}, format="json")
                         .json()["error"]["code"], "account_restricted")
        invite = self.customer.post(reverse("job-invitations", args=[make_invitation(self.customer_user, make_worker()).job_id]),
                                    {"worker_id": str(make_worker().id)}, format="json")
        self.assertEqual(invite.json()["error"]["code"], "account_restricted")
        self.assertEqual(self.customer.post(reverse("bookings"), accept_body(quote), format="json").json()["error"]["code"], "account_restricted")
        self.assertEqual(self.customer.post(reverse("report-replies", args=[report["id"]]), {"text": "یہ رہی معلومات"}, format="json").status_code, 201)
        self.assertEqual(self.customer.get(reverse("auth-me")).json()["user"]["restricted"], True)
        User.objects.filter(pk=self.customer_user.pk).update(restricted_at=None)
        self.assertEqual(self.customer.post(reverse("bookings"), accept_body(quote), format="json").status_code, 201)


class BlockTests(ReportTestCase):
    def test_blocking_stops_messages_and_invitations_but_keeps_history_and_the_booking(self):
        self.assertEqual(self.message(self.worker, "پہلا پیغام").status_code, 201)
        block = self.customer.post(reverse("blocks"), {"invitation_id": str(self.invitation.id)}, format="json")
        self.assertEqual(block.status_code, 201, block.content)
        for client in (self.customer, self.worker):
            self.assertEqual(self.message(client).json()["error"]["code"], "contact_blocked")
        history = self.worker.get(reverse("conversation-messages", args=[self.invitation.id])).json()["results"]
        self.assertEqual([m["text"] for m in history], ["پہلا پیغام"])  # history kept
        mine = self.customer.get(reverse("conversation", args=[self.invitation.id])).json()["contact_block"]
        theirs = self.worker.get(reverse("conversation", args=[self.invitation.id])).json()
        self.assertEqual((mine["blocked"], mine["by_me"]), (True, True))
        self.assertEqual((theirs["contact_block"], theirs["write_blocked_reason"]), ({"blocked": True, "by_me": False, "block_id": None}, "contact_blocked"))
        # No new invitation between the pair, and the worker is not recommended to this customer.
        job = make_invitation(self.customer_user, make_worker())
        Invitation.objects.filter(pk=job.pk).update(status="withdrawn", closed_at=timezone.now())
        invite = self.customer.post(reverse("job-invitations", args=[job.job_id]), {"worker_id": str(self.profile.id)}, format="json")
        self.assertEqual(invite.json()["error"]["code"], "contact_blocked")
        ids = [w["worker_id"] for w in self.customer.get(reverse("job-recommendations", args=[job.job_id])).json()["workers"]]
        self.assertNotIn(str(self.profile.id), ids)
        # The other person cannot lift someone else's block; the blocker can.
        self.assertEqual(self.worker.delete(reverse("block", args=[block.json()["id"]])).status_code, 404)
        self.assertEqual(self.customer.delete(reverse("block", args=[block.json()["id"]])).status_code, 204)
        self.assertEqual(self.message(self.worker).status_code, 201)

    def test_a_block_during_a_booking_keeps_its_completion_and_dispute_actions(self):
        booking = started(self.customer_user, self.profile, at(3, 10))
        self.assertEqual(self.worker.post(reverse("blocks"), {"booking_id": str(booking.pk)}, format="json").status_code, 201)
        payload = self.customer.get(reverse("booking", args=[booking.pk])).json()
        self.assertEqual((payload["status"], payload["contact_block"]["blocked"]), ("in_progress", True))
        self.assertEqual(self.worker.post(reverse("booking-request-completion", args=[booking.pk])).status_code, 200)
        issue = self.customer.post(reverse("booking-raise-issue", args=[booking.pk]), {"reason": "not_finished", "note": "ابھی باقی ہے"}, format="json")
        self.assertEqual(issue.json()["status"], "disputed")
        self.assertEqual(Booking.objects.get(pk=booking.pk).status, "disputed")
        self.assertEqual(ContactBlock.objects.count(), 1)


class RetentionTests(ReportTestCase):
    def test_purge_removes_old_closed_evidence_only(self):
        old_id = self.file(self.customer).json()["id"]
        clip = self.report_clip(self.customer)
        self.customer.post(reverse("report-evidence", args=[old_id]), {"audio_clip_id": clip["id"]}, format="json")
        self.customer.post(reverse("report-evidence", args=[old_id]), {"file": SimpleUploadedFile("e.png", png(), content_type="image/png")},
                           format="multipart")
        open_id = self.file(self.customer).json()["id"]
        self.customer.post(reverse("report-evidence", args=[open_id]), {"file": SimpleUploadedFile("e.png", png(), content_type="image/png")},
                           format="multipart")
        services.decide(staff_with("review_report"), old_id, action="resolve", reason="Done", message_to_reporter="Closed")
        Report.objects.filter(pk=old_id).update(closed_at=timezone.now() - timedelta(days=400))
        call_command("purge_report_evidence", "--days", "180", stdout=io.StringIO())
        removed = ReportEvidence.objects.filter(report_id=old_id)
        self.assertTrue(all(e.deleted_at is not None and not e.file and e.audio_clip_id is None for e in removed))
        self.assertFalse(AudioClip.objects.filter(pk=clip["id"]).exists())
        self.assertTrue(Report.objects.filter(pk=old_id).exists())  # the report and its decisions stay
        kept = ReportEvidence.objects.get(report_id=open_id)
        self.assertIsNone(kept.deleted_at)  # open case: preserved
        payload = self.customer.get(reverse("report", args=[old_id])).json()["evidence"]
        self.assertTrue(all(e["removed"] and e["content_url"] is None for e in payload))

    def test_evidence_of_an_active_dispute_is_preserved(self):
        booking = started(self.customer_user, self.profile, at(3, 10))
        report_id = self.customer.post(reverse("reports"), {"client_id": str(uuid.uuid4()), "booking_id": str(booking.pk), "category": "property_work",
                                                            "description": "نقصان"}, format="json").json()["id"]
        self.customer.post(reverse("report-evidence", args=[report_id]), {"file": SimpleUploadedFile("e.png", png(), content_type="image/png")},
                           format="multipart")
        bookings.request_completion(self.profile.user, booking.pk)
        bookings.raise_issue(self.customer_user, booking.pk, reason="damage", note="دیوار")
        services.decide(staff_with("review_report"), report_id, action="dismiss", reason="Duplicate of dispute", message_to_reporter="Closed")
        Report.objects.filter(pk=report_id).update(closed_at=timezone.now() - timedelta(days=400))
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            call_command("purge_report_evidence", "--days", "1", stdout=io.StringIO())
        self.assertIsNone(ReportEvidence.objects.get(report_id=report_id).deleted_at)

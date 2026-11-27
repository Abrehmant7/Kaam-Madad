import json
import threading
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.bookings import services
from apps.bookings.models import ArrivalCode, Booking, BookingChange
from apps.conversations import quotes as rules
from apps.conversations.models import GapFinding, Quote
from apps.conversations.views import submit_draft
from apps.core.api.exceptions import ApiError
from apps.invitations.models import Invitation
from apps.invitations.tests.helpers import KARACHI, PASSWORD, User, client_for, make_confirmed_job, make_worker, next_phone, seed
from apps.jobs.summary import matching_summary
from apps.providers.agreement import AgreementResult

MATERIALS_INCLUDED = "دو پنکھے لگوانے ہیں۔ 1200 روپے سامان سمیت۔"


def at(days: int, hour: int):
    return (timezone.now() + timedelta(days=days)).astimezone(KARACHI).replace(hour=hour, minute=0, second=0, microsecond=0)


def make_invitation(customer, profile, **job_kwargs):
    job = make_confirmed_job(customer, **job_kwargs)
    return Invitation.objects.create(job=job, worker_profile=profile, shared_summary=matching_summary(job))


def ready_quote(invitation, *, start=None, hours=2, version=1, materials="included"):
    """A submitted version whose check passed (built directly; the API path is tested in AcceptanceApiTests)."""
    now = timezone.now()
    start = start or at(1, 17)
    quote = Quote(invitation=invitation, status="submitted", version=version, scope="Install two ceiling fans", quantity=2,
                  labour_amount=Decimal("600"), labour_basis="per_item", materials=materials, start_at=start,
                  end_at=start + timedelta(hours=hours), submitted_at=now, expires_at=rules.expiry_for(now, start),
                  check_status="passed", check_provider="fixture", check_simulated=True, checked_at=now)
    quote.totals = rules.compute_totals(quote)
    quote.save()
    return quote


def accept_body(quote, key=None):
    return {"invitation_id": str(quote.invitation_id), "quote_id": str(quote.id), "version": quote.version,
            "idempotency_key": str(key or uuid.uuid4())}


class BookingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.customer_user = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        self.customer = client_for(self.customer_user)
        self.profile = make_worker()
        self.worker = client_for(self.profile.user)
        self.invitation = make_invitation(self.customer_user, self.profile)
        self.quote = ready_quote(self.invitation)

    def accept(self, quote=None, key=None, client=None):
        return (client or self.customer).post(reverse("bookings"), accept_body(quote or self.quote, key), format="json")

    def booked(self):
        response = self.accept()
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def act(self, client, name, booking_id, body=None):
        return client.post(reverse(name, args=[booking_id]), body or {}, format="json")


class AcceptanceTests(BookingTestCase):
    def test_accept_creates_one_booking_with_the_exact_terms_and_retries_return_it(self):
        key = uuid.uuid4()
        first = self.accept(key=key)
        self.assertEqual(first.status_code, 201, first.content)
        booking = first.json()
        self.assertEqual((booking["status"], booking["quote_version"], booking["created"]), ("confirmed", 1, True))
        self.assertEqual(booking["accepted_terms"]["labour_amount"], "600.00")
        self.assertEqual(booking["accepted_terms"]["totals"]["known_total"], "1200.00")
        self.assertEqual(booking["terms"]["start_at"], rules.iso_utc(self.quote.start_at))
        self.assertEqual(booking["history"][0]["kind"], "confirmed")

        again = self.accept(key=key)  # e.g. the response was lost: the same booking, not a second one
        self.assertEqual((again.status_code, again.json()["id"], again.json()["created"]), (200, booking["id"], False))
        other_key = self.accept()
        self.assertEqual(other_key.status_code, 409)
        self.assertEqual(other_key.json()["error"]["code"], "job_already_booked")
        self.assertEqual(other_key.json()["error"]["details"]["booking_id"], booking["id"])
        reused = self.customer.post(reverse("bookings"), {**accept_body(self.quote, key), "quote_id": str(uuid.uuid4())}, format="json")
        self.assertEqual(reused.json()["error"]["code"], "idempotency_key_reused")
        self.assertEqual(Booking.objects.count(), 1)

        worker_view = self.worker.get(reverse("booking", args=[booking["id"]])).json()
        self.assertEqual(worker_view["accepted_terms"], booking["accepted_terms"])  # both see the same booking
        self.assertEqual(worker_view["counterpart"], {"role": "customer"})
        self.assertIsNone(worker_view["job_id"])

    def test_only_the_owner_can_accept_and_others_cannot_open_the_booking(self):
        self.assertEqual(self.accept(client=self.worker).status_code, 403)
        stranger = client_for(User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER))
        self.assertEqual(self.accept(client=stranger).status_code, 404)
        booking = self.booked()
        other_worker = client_for(make_worker().user)
        for client in (stranger, other_worker):
            self.assertEqual(client.get(reverse("booking", args=[booking["id"]])).status_code, 404)
            for name in ("booking-arrive", "booking-arrival-code", "booking-cancel"):
                self.assertEqual(self.act(client, name, booking["id"], {"reason": "other", "note": "xyz"}).status_code, 404)
        self.assertNotIn(booking["id"], json.dumps(stranger.get(reverse("bookings")).json()))

    def test_stale_expired_and_blocked_quotes_are_refused(self):
        Quote.objects.filter(pk=self.quote.pk).update(status="superseded", superseded_at=timezone.now())
        newer = ready_quote(self.invitation, version=2)
        stale = self.accept()
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"]["code"], "quote_not_current")
        self.assertEqual(stale.json()["error"]["details"], {"current_quote_id": str(newer.id), "current_version": 2})

        with mock.patch("django.utils.timezone.now", return_value=newer.expires_at + timedelta(seconds=1)):
            self.assertEqual(self.accept(newer).json()["error"]["code"], "quote_expired")

        GapFinding.objects.create(quote=newer, source="ai", code="materials_responsibility", question="?", ask="worker",
                                  sources=[{"kind": "quote", "ref": "materials", "text": "included"}])
        blocked = self.accept(newer).json()["error"]
        self.assertEqual((blocked["code"], blocked["details"]["blocking"]), ("quote_not_ready", ["unresolved_findings"]))
        self.assertFalse(Booking.objects.exists())

    def test_a_paused_worker_can_still_be_booked_but_an_ineligible_one_cannot(self):
        self.profile.accepting_requests = False
        self.profile.save()
        self.assertEqual(self.accept().status_code, 201)  # pausing controls new requests only
        other = make_invitation(self.customer_user, make_worker(identity="in_progress"))
        response = self.accept(ready_quote(other))
        self.assertEqual(response.json()["error"]["code"], "worker_not_eligible")

    def test_overlapping_times_conflict_and_adjacent_times_do_not(self):
        self.booked()  # 17:00–19:00 tomorrow
        second_customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        overlapping = ready_quote(make_invitation(second_customer, self.profile), start=at(1, 18))
        response = client_for(second_customer).post(reverse("bookings"), accept_body(overlapping), format="json")
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "schedule_conflict"))
        adjacent = ready_quote(make_invitation(second_customer, self.profile), start=at(1, 19))  # [17,19) then [19,21)
        self.assertEqual(client_for(second_customer).post(reverse("bookings"), accept_body(adjacent), format="json").status_code, 201)

    def test_after_booking_quotes_and_invitations_are_frozen_but_messages_continue(self):
        booking = self.booked()
        url = lambda name, *args: reverse(name, args=[self.invitation.id, *args])  # noqa: E731
        draft = self.worker.put(url("conversation-quote-draft"), {"scope": "x"}, format="json")
        self.assertEqual((draft.status_code, draft.json()["error"]["code"]), (409, "job_already_booked"))
        self.assertEqual(self.worker.post(url("conversation-quote-submit")).status_code, 409)
        withdraw = self.customer.post(reverse("job-invitation-withdraw", args=[self.invitation.job_id, self.invitation.id]))
        self.assertEqual(withdraw.json()["error"]["code"], "invitation_booked")
        self.assertEqual(withdraw.json()["error"]["details"]["booking_id"], booking["id"])
        decline = self.worker.post(reverse("invitation-decline", args=[self.invitation.id]), {}, format="json")
        self.assertEqual(decline.json()["error"]["code"], "invitation_booked")
        invite = self.customer.post(reverse("job-invitations", args=[self.invitation.job_id]),
                                    {"worker_id": str(make_worker().id)}, format="json")
        self.assertEqual(invite.json()["error"]["code"], "job_already_booked")
        message = self.worker.post(url("conversation-messages"), {"client_id": str(uuid.uuid4()), "kind": "text",
                                                                 "text": "میں راستے میں ہوں"}, format="json")
        self.assertEqual(message.status_code, 201)
        header = self.customer.get(url("conversation")).json()
        self.assertEqual(header["booking"], {"id": booking["id"], "status": "confirmed"})
        self.assertEqual(self.customer.get(reverse("job", args=[self.invitation.job_id])).json()["booking"]["id"], booking["id"])
        self.quote.refresh_from_db()
        self.assertEqual((self.quote.status, self.quote.version), ("submitted", 1))  # the original quote is unchanged

    def test_the_exact_address_reaches_only_the_assigned_worker_after_booking(self):
        url = reverse("conversation", args=[self.invitation.id])
        self.assertNotIn("House 5", json.dumps(self.worker.get(url).json()))
        booking = self.booked()
        worker_view = self.worker.get(reverse("booking", args=[booking["id"]])).json()
        self.assertEqual(worker_view["address"], {"address": "House 5, Street 9", "access_notes": "Ring twice"})
        self.assertNotIn("House 5", json.dumps(self.worker.get(url).json()))  # never in the conversation or invitation
        self.assertNotIn("House 5", json.dumps(self.worker.get(reverse("invitation", args=[self.invitation.id])).json()))
        self.act(self.worker, "booking-cancel", booking["id"], {"reason": "not_available"})
        self.assertIsNone(self.worker.get(reverse("booking", args=[booking["id"]])).json()["address"])

    def test_accepted_terms_cannot_be_overwritten(self):
        booking = Booking.objects.get(pk=self.booked()["id"])
        booking.accepted_terms = {**booking.accepted_terms, "labour_amount": "1.00"}
        with self.assertRaises(ValueError):
            booking.save()


class AgreementHandoffTests(BookingTestCase):
    """M7 fixes: "terms changed" needs a revised quote; a running check blocks; late results are discarded."""

    def setUp(self):
        super().setUp()
        self.job = make_confirmed_job(self.customer_user, description=MATERIALS_INCLUDED)
        self.inv2 = Invitation.objects.create(job=self.job, worker_profile=self.profile, shared_summary=matching_summary(self.job))
        self.url = lambda name, *args: reverse(name, args=[self.inv2.id, *args])  # noqa: E731

    def submit(self, **terms):
        body = {"inspection_only": False, "scope": "Install two ceiling fans", "quantity": 2, "labour_amount": "600",
                "labour_basis": "per_item", "materials": "customer", "materials_amount": None, "visit_fee": None,
                "visit_fee_treatment": "none", "exclusions": "", "start_at": at(1, 17).isoformat(), "end_at": at(1, 19).isoformat()}
        body.update(terms)
        self.assertEqual(self.worker.put(self.url("conversation-quote-draft"), body, format="json").status_code, 200)
        response = self.worker.post(self.url("conversation-quote-submit"))
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_terms_changed_keeps_the_version_blocked_until_a_revised_quote(self):
        v1 = self.submit()
        finding = next(f for f in v1["findings"] if f["code"] == "materials_responsibility")
        resolved = self.customer.post(self.url("conversation-finding-resolve", v1["id"], finding["id"]),
                                      {"resolution": "terms_changed", "note": "کاریگر سامان لائیں گے، کل 1500"}, format="json").json()
        self.assertEqual(resolved["readiness"]["blocking"], ["revision_required"])
        refused = self.customer.post(reverse("bookings"), {**accept_body(Quote.objects.get(pk=v1["id"]))}, format="json")
        self.assertEqual(refused.json()["error"]["details"]["blocking"], ["revision_required"])

        v2 = self.submit(labour_basis="total", labour_amount="1500", materials="included")
        self.assertEqual((v2["version"], v2["check"]["status"]), (2, "passed"))
        accepted = self.customer.post(reverse("bookings"), accept_body(Quote.objects.get(pk=v2["id"])), format="json")
        self.assertEqual(accepted.status_code, 201, accepted.content)
        history = self.customer.get(self.url("conversation-quotes")).json()["history"][0]
        self.assertEqual((history["version"], history["findings"][0]["resolution"]), (1, "terms_changed"))

    def test_terms_confirmed_resolves_the_version(self):
        v1 = self.submit()
        finding = v1["findings"][0]
        resolved = self.customer.post(self.url("conversation-finding-resolve", v1["id"], finding["id"]),
                                      {"resolution": "terms_confirmed", "note": "میں سامان خود خریدوں گا"}, format="json").json()
        self.assertTrue(resolved["readiness"]["ready"], resolved["readiness"])

    def test_a_running_check_blocks_acceptance_and_a_stalled_one_allows_manual_review(self):
        quote = ready_quote(self.inv2)
        attempt = rules.begin_check(quote)
        self.assertIsNotNone(attempt)
        self.assertEqual(rules.readiness(self.inv2)["blocking"], ["automated_check_running"])
        refused = self.customer.post(reverse("bookings"), accept_body(quote), format="json").json()["error"]
        self.assertEqual(refused["details"]["blocking"], ["automated_check_running"])
        self.assertEqual(self.customer.post(self.url("conversation-quote-manual-review", quote.id)).status_code, 409)

        Quote.objects.filter(pk=quote.pk).update(check_started_at=timezone.now() - timedelta(hours=1))  # the run died
        payload = self.customer.get(self.url("conversation-quotes")).json()
        self.assertEqual((payload["current"]["check"]["status"], payload["current"]["check"]["failure"]), ("unavailable", "stalled"))
        self.assertEqual(self.customer.post(self.url("conversation-quote-manual-review", quote.id)).status_code, 200)
        self.assertTrue(rules.readiness(self.inv2)["ready"])

    def test_a_late_result_from_an_older_attempt_is_discarded(self):
        quote = ready_quote(self.inv2)
        first = rules.begin_check(quote)
        second = rules.begin_check(quote)  # re-run started; the first is now stale
        late = AgreementResult(findings=[{"code": "other", "ask": "both", "question": "late?", "sources": []}],
                               provider="fixture", model="x", simulated=True)
        self.assertFalse(rules.store_check_result(quote.pk, first, result=late))
        self.assertTrue(rules.store_check_result(quote.pk, second, result=AgreementResult(provider="fixture", simulated=True)))
        quote.refresh_from_db()
        self.assertEqual((quote.check_status, quote.findings.count()), ("passed", 0))

    def test_a_result_arriving_after_acceptance_or_supersession_is_discarded(self):
        quote = ready_quote(self.inv2)
        attempt = rules.begin_check(quote)
        Quote.objects.filter(pk=quote.pk).update(check_status="passed")  # e.g. the customer accepted meanwhile …
        response = self.customer.post(reverse("bookings"), accept_body(quote), format="json")
        self.assertEqual(response.status_code, 201)
        finding = AgreementResult(findings=[{"code": "other", "ask": "both", "question": "?", "sources": []}],
                                  provider="fixture", model="x", simulated=True)
        self.assertFalse(rules.store_check_result(quote.pk, attempt, failure="ai_provider_unavailable:timeout"))
        self.assertFalse(rules.store_check_result(quote.pk, attempt, result=finding))
        quote.refresh_from_db()
        self.assertEqual((quote.check_status, quote.findings.count()), ("passed", 0))  # the approval record is stable
        booking = Booking.objects.get()
        self.assertEqual(booking.accepted_terms["check"]["status"], "passed")
        self.assertIsNone(rules.begin_check(quote))  # an accepted version is never re-checked


class ArrivalCodeTests(BookingTestCase):
    def setUp(self):
        super().setUp()
        self.booking = self.booked()
        self.id = self.booking["id"]

    def issue(self):
        response = self.act(self.customer, "booking-arrival-code", self.id)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["code"]["value"]

    def start(self, code):
        return self.act(self.worker, "booking-start", self.id, {"code": code})

    def test_only_after_arrival_only_the_customer_and_never_to_the_worker(self):
        self.assertEqual(self.act(self.customer, "booking-arrival-code", self.id).json()["error"]["code"], "booking_state_conflict")
        self.assertEqual(self.act(self.customer, "booking-arrive", self.id).status_code, 403)
        arrived = self.act(self.worker, "booking-arrive", self.id).json()
        self.assertEqual(arrived["status"], "arrived")
        self.assertEqual(self.act(self.worker, "booking-arrival-code", self.id).status_code, 403)
        with self.assertLogs("apps.bookings", level="INFO") as logs:
            code = self.issue()
        self.assertRegex(code, r"^\d{6}$")
        self.assertNotIn(code, "\n".join(logs.output))
        stored = ArrivalCode.objects.get()
        self.assertNotIn(code, stored.digest)
        for client in (self.worker, self.customer):  # never again in any response, for either role
            body = client.get(reverse("booking", args=[self.id])).content.decode()
            self.assertNotIn(code, body)
            self.assertNotIn(stored.digest, body)
        state = self.worker.get(reverse("booking", args=[self.id])).json()["arrival_code"]
        self.assertEqual((state["active"], state["attempts_remaining"]), (True, 5))

    def test_wrong_attempts_are_counted_and_lock_the_code_and_reissue_invalidates_it(self):
        self.act(self.worker, "booking-arrive", self.id)
        code = self.issue()
        wrong = "000000" if code != "000000" else "111111"
        first = self.start(wrong)
        self.assertEqual((first.status_code, first.json()["error"]["code"]), (400, "code_incorrect"))
        self.assertEqual(first.json()["error"]["details"]["attempts_remaining"], 4)
        self.assertEqual(ArrivalCode.objects.get().failed_attempts, 1)  # persisted although the call failed
        for _ in range(3):
            self.start(wrong)
        fifth = self.start(wrong)
        self.assertEqual((fifth.status_code, fifth.json()["error"]["code"]), (429, "too_many_attempts"))
        self.assertEqual(self.start(code).json()["error"]["code"], "too_many_attempts")  # locked, even the right code
        self.assertEqual(self.start("12 34").status_code, 400)  # format error, not an attempt

        new = self.issue()
        old = ArrivalCode.objects.exclude(invalidated_at=None).get()
        self.assertEqual(old.failed_attempts, 5)
        if new != code:
            self.assertEqual(self.start(code).json()["error"]["code"], "code_incorrect")  # the old code no longer works
        started = self.start(new)
        self.assertEqual(started.status_code, 200, started.content)
        self.assertEqual(started.json()["status"], "in_progress")
        self.assertEqual(self.start(new).json()["status"], "in_progress")  # a retry; the code is single-use
        self.assertEqual(ArrivalCode.objects.filter(used_at__isnull=False).count(), 1)
        history = [e["kind"] for e in started.json()["history"]]
        self.assertEqual(history[0], "confirmed")
        self.assertIn("arrived", history)
        self.assertEqual(history[-1], "started")

    def test_expired_and_missing_codes(self):
        self.act(self.worker, "booking-arrive", self.id)
        self.assertEqual(self.start("123456").json()["error"]["code"], "no_active_code")
        code = self.issue()
        expires = ArrivalCode.objects.get().expires_at
        self.assertAlmostEqual((expires - timezone.now()).total_seconds(), 15 * 60, delta=5)
        with mock.patch("django.utils.timezone.now", return_value=expires + timedelta(seconds=1)):
            self.assertEqual(self.start(code).json()["error"]["code"], "code_expired")
        self.assertEqual(self.act(self.customer, "booking-start", self.id, {"code": code}).status_code, 403)

    def test_a_worker_with_a_job_in_progress_cannot_start_another(self):
        self.act(self.worker, "booking-arrive", self.id)
        self.assertEqual(self.start(self.issue()).status_code, 200)
        other_customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        later = ready_quote(make_invitation(other_customer, self.profile), start=at(2, 10))  # no overlap at all
        second = client_for(other_customer).post(reverse("bookings"), accept_body(later), format="json").json()
        self.act(self.worker, "booking-arrive", second["id"])
        code = client_for(other_customer).post(reverse("booking-arrival-code", args=[second["id"]])).json()["code"]["value"]
        response = self.act(self.worker, "booking-start", second["id"], {"code": code})
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "worker_has_job_in_progress"))
        self.assertEqual(ArrivalCode.objects.get(booking_id=second["id"]).failed_attempts, 0)


class CancellationTests(BookingTestCase):
    def test_cancel_before_start_releases_the_slot_and_closes_the_invitation(self):
        booking = self.booked()
        missing = self.act(self.customer, "booking-cancel", booking["id"], {"reason": "other"})
        self.assertEqual(missing.status_code, 400)
        cancelled = self.act(self.worker, "booking-cancel", booking["id"], {"reason": "not_available", "note": "بیمار ہوں"}).json()
        self.assertEqual((cancelled["status"], cancelled["cancelled_role"], cancelled["cancel_reason"]),
                         ("cancelled", "worker", "not_available"))
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, "cancelled")
        reuse = self.accept()  # the old quote cannot be accepted again
        self.assertEqual(reuse.json()["error"]["code"], "invitation_not_active")
        other_customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        same_time = ready_quote(make_invitation(other_customer, self.profile))
        self.assertEqual(client_for(other_customer).post(reverse("bookings"), accept_body(same_time), format="json").status_code, 201)
        again = self.customer.post(reverse("job-invitations", args=[self.invitation.job_id]),
                                   {"worker_id": str(make_worker().id)}, format="json")
        self.assertEqual(again.status_code, 201)  # the customer can invite someone else for the request

    def test_no_cancellation_after_the_job_started(self):
        booking = self.booked()
        self.act(self.worker, "booking-arrive", booking["id"])
        code = self.act(self.customer, "booking-arrival-code", booking["id"]).json()["code"]["value"]
        self.act(self.worker, "booking-start", booking["id"], {"code": code})
        response = self.act(self.customer, "booking-cancel", booking["id"], {"reason": "changed_plans"})
        self.assertEqual(response.json()["error"]["code"], "cancel_not_allowed")


class ChangeTests(BookingTestCase):
    def terms(self, booking, **overrides):
        current = booking["terms"]
        body = {name: current[name] for name in services.TERM_FIELDS}
        body["materials"] = body["materials"] or ""
        body.update(overrides)
        return body

    def test_a_change_needs_both_approvals_and_keeps_the_original_agreement(self):
        booking = self.booked()
        proposed = self.terms(booking, quantity=3, note="تیسرا پنکھا بھی")
        response = self.act(self.worker, "booking-changes", booking["id"], proposed)
        self.assertEqual(response.status_code, 200, response.content)
        pending = response.json()
        change = pending["changes"][0]
        self.assertEqual((change["status"], change["new_terms"]["totals"]["known_total"]), ("pending", "1800.00"))
        self.assertEqual(pending["terms"]["quantity"], 2)  # not in effect yet
        self.assertEqual(self.worker.post(reverse("booking-change-approve", args=[booking["id"], change["id"]])).status_code, 403)
        self.assertEqual(self.act(self.worker, "booking-changes", booking["id"], proposed).json()["error"]["code"], "change_pending")
        approved = self.customer.post(reverse("booking-change-approve", args=[booking["id"], change["id"]])).json()
        self.assertEqual((approved["terms"]["quantity"], approved["terms"]["totals"]["known_total"]), (3, "1800.00"))
        self.assertTrue(approved["terms_changed"])
        self.assertEqual(approved["accepted_terms"]["quantity"], 2)  # the original agreement stays in history
        self.assertEqual(approved["changes"][0]["old_terms"]["quantity"], 2)
        self.assertEqual([e["kind"] for e in approved["history"]][-2:], ["change_proposed", "change_approved"])

    def test_time_changes_recheck_overlaps_and_only_before_arrival(self):
        booking = self.booked()
        other_customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        client_for(other_customer).post(reverse("bookings"), accept_body(ready_quote(make_invitation(other_customer, self.profile),
                                                                                     start=at(1, 20))), format="json")
        clash = self.terms(booking, start_at=at(1, 19).isoformat(), end_at=at(1, 21).isoformat(), note="ایک گھنٹہ بعد")
        self.assertEqual(self.act(self.customer, "booking-changes", booking["id"], clash).json()["error"]["code"], "schedule_conflict")
        later = self.terms(booking, start_at=at(2, 17).isoformat(), end_at=at(2, 19).isoformat(), note="اگلے دن")
        change = self.act(self.customer, "booking-changes", booking["id"], later).json()["changes"][0]
        # Another booking takes that slot before the worker approves: re-checked under the worker lock.
        third = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        client_for(third).post(reverse("bookings"), accept_body(ready_quote(make_invitation(third, self.profile), start=at(2, 18))),
                               format="json")
        refused = self.worker.post(reverse("booking-change-approve", args=[booking["id"], change["id"]]))
        self.assertEqual(refused.json()["error"]["code"], "schedule_conflict")
        self.assertEqual(Booking.objects.get(pk=booking["id"]).start_at, self.quote.start_at)
        self.worker.post(reverse("booking-change-reject", args=[booking["id"], change["id"]]))

        self.act(self.worker, "booking-arrive", booking["id"])
        moved = self.terms(booking, start_at=at(3, 17).isoformat(), end_at=at(3, 19).isoformat(), note="بعد میں")
        self.assertEqual(self.act(self.customer, "booking-changes", booking["id"], moved).json()["error"]["code"],
                         "time_change_not_allowed")
        same = self.act(self.customer, "booking-changes", booking["id"], self.terms(booking, note="کچھ نہیں"))
        self.assertEqual(same.json()["error"]["fields"]["non_field_errors"][0]["code"], "no_change")

    def test_a_scope_change_during_the_job_and_withdrawal_by_the_proposer(self):
        booking = self.booked()
        self.act(self.worker, "booking-arrive", booking["id"])
        code = self.act(self.customer, "booking-arrival-code", booking["id"]).json()["code"]["value"]
        self.act(self.worker, "booking-start", booking["id"], {"code": code})
        with mock.patch("django.utils.timezone.now", return_value=self.quote.start_at + timedelta(minutes=30)):
            proposed = self.act(self.worker, "booking-changes", booking["id"], self.terms(booking, quantity=3, note="تیسرا پنکھا"))
            self.assertEqual(proposed.status_code, 200, proposed.content)  # past start time is fine when it is unchanged
        change = proposed.json()["changes"][0]
        self.assertEqual(self.customer.post(reverse("booking-change-withdraw", args=[booking["id"], change["id"]])).status_code, 403)
        withdrawn = self.worker.post(reverse("booking-change-withdraw", args=[booking["id"], change["id"]])).json()
        self.assertEqual((withdrawn["changes"][0]["status"], withdrawn["terms"]["quantity"]), ("withdrawn", 2))


class BookingConcurrencyTests(TransactionTestCase):
    """Real concurrent transactions on PostgreSQL (separate connections, released together by a barrier)."""

    def setUp(self):
        seed()
        self.profile = make_worker()

    def _race(self, *actions):
        barrier = threading.Barrier(len(actions))
        outcomes = []

        def run(action):
            try:
                barrier.wait()
                outcomes.append(action())
            except ApiError as exc:
                outcomes.append(exc.default_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(a,)) for a in actions]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        return outcomes

    def _customer_quote(self, start):
        customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        return customer, ready_quote(make_invitation(customer, self.profile), start=start)

    def _accept(self, customer, quote, key=None):
        return lambda: services.accept_quote(customer, invitation_id=quote.invitation_id, quote_id=quote.id,
                                             version=quote.version, key=key or uuid.uuid4())[0]

    def test_two_customers_accepting_overlapping_slots_get_one_booking(self):
        for day in (1, 2, 3):
            a, qa = self._customer_quote(at(day, 17))
            b, qb = self._customer_quote(at(day, 18))
            outcomes = self._race(self._accept(a, qa), self._accept(b, qb))
            self.assertEqual(sorted(type(o).__name__ if isinstance(o, Booking) else o for o in outcomes),
                             ["Booking", "schedule_conflict"])
        self.assertEqual(Booking.objects.count(), 3)

    def test_a_double_tap_with_one_key_gives_one_booking(self):
        customer, quote = self._customer_quote(at(1, 17))
        key = uuid.uuid4()
        outcomes = self._race(self._accept(customer, quote, key), self._accept(customer, quote, key))
        self.assertEqual(Booking.objects.count(), 1)
        self.assertTrue(all(isinstance(o, Booking) and o.pk == outcomes[0].pk for o in outcomes), outcomes)

    def test_accept_against_withdrawal(self):
        from apps.invitations.views import WithdrawView  # noqa: F401 - the view's rule is exercised through its helper

        for day in (1, 2, 3):
            customer, quote = self._customer_quote(at(day, 17))

            def withdraw():
                with transaction.atomic():
                    invitation = Invitation.objects.select_for_update().get(pk=quote.invitation_id)
                    if services.booking_for_invitation(invitation.pk):
                        return "invitation_booked"
                    invitation.status, invitation.closed_at = "withdrawn", timezone.now()
                    invitation.save()
                    return "withdrawn"

            outcomes = self._race(self._accept(customer, quote), withdraw)
            invitation = Invitation.objects.get(pk=quote.invitation_id)
            booked = Booking.objects.filter(invitation=invitation).exists()
            if booked:
                self.assertEqual((invitation.status, outcomes.count("invitation_booked")), ("active", 1))
            else:
                self.assertEqual(invitation.status, "withdrawn")
                self.assertIn("invitation_not_active", outcomes)

    def test_accept_against_a_revision(self):
        for day in (1, 2, 3):
            customer, quote = self._customer_quote(at(day, 17))
            Quote.objects.create(invitation=quote.invitation, scope="Three fans", quantity=3, labour_amount=Decimal("600"),
                                 labour_basis="per_item", materials="included", start_at=at(day, 17), end_at=at(day, 19))
            outcomes = self._race(self._accept(customer, quote), lambda: submit_draft(quote.invitation_id, self.profile.user))
            booking = Booking.objects.filter(invitation_id=quote.invitation_id).first()
            if booking:  # accepted first: the revision was refused and v1 stays the accepted, current version
                self.assertIn("job_already_booked", outcomes)
                self.assertEqual((booking.quote_version, Quote.objects.get(pk=quote.pk).status), (1, "submitted"))
            else:
                self.assertIn("quote_not_current", outcomes)
                self.assertEqual(Quote.objects.get(pk=quote.pk).status, "superseded")

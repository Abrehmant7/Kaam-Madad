import json
import threading
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from apps.bookings import services
from apps.bookings.models import Booking, BookingEvent
from apps.bookings.tests.test_bookings import accept_body, at, make_invitation, ready_quote
from apps.core.api.exceptions import ApiError
from apps.invitations.matching import recommend
from apps.invitations.tests.helpers import PASSWORD, User, client_for, make_worker, next_phone, seed
from apps.jobs.summary import matching_summary
from apps.reviews.models import Review
from apps.reviews.services import submit_review, worker_stats
from apps.voice.tests.helpers import make_wav


def started(customer, profile, start):
    """A booking taken all the way to in_progress through the real M8 services."""
    quote = ready_quote(make_invitation(customer, profile), start=start)
    booking, _ = services.accept_quote(customer, invitation_id=quote.invitation_id, quote_id=quote.id, version=1, key=uuid.uuid4())
    services.mark_arrived(profile.user, booking.pk)
    code, _ = services.issue_code(customer, booking.pk)
    services.start_with_code(profile.user, booking.pk, code)
    return Booking.objects.get(pk=booking.pk)


def staff_with(*codenames):
    user = User.objects.create_user(next_phone(), PASSWORD, is_staff=True)
    user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    return User.objects.get(pk=user.pk)  # fresh permission cache


class CompletionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed()

    def setUp(self):
        self.customer_user = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        self.customer = client_for(self.customer_user)
        self.profile = make_worker()
        self.worker = client_for(self.profile.user)
        self.booking = started(self.customer_user, self.profile, at(1, 17))
        self.id = str(self.booking.pk)

    def post(self, client, name, body=None, booking_id=None):
        return client.post(reverse(name, args=[booking_id or self.id]), body or {}, format="json")

    def to_completion_requested(self):
        response = self.post(self.worker, "booking-request-completion")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def complete(self):
        self.to_completion_requested()
        response = self.post(self.customer, "booking-confirm-completion")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class CompletionTests(CompletionTestCase):
    def test_worker_requests_customer_confirms_and_the_worker_is_released(self):
        self.profile.accepting_requests = False  # paused before: must stay paused after completion
        self.profile.save()
        requested = self.to_completion_requested()
        self.assertEqual((requested["status"], requested["actions"]["confirm_completion"]), ("completion_requested", False))
        self.assertEqual(self.post(self.worker, "booking-request-completion").status_code, 200)  # retry: no 2nd event
        self.assertEqual(self.post(self.worker, "booking-confirm-completion").status_code, 403)  # never unilateral
        customer_view = self.customer.get(reverse("booking", args=[self.id])).json()
        self.assertTrue(customer_view["actions"]["confirm_completion"] and customer_view["actions"]["raise_issue"])

        done = self.post(self.customer, "booking-confirm-completion").json()
        self.assertEqual(self.post(self.customer, "booking-confirm-completion").status_code, 200)  # retry
        self.assertEqual((done["status"], done["completed_services"]), ("completed", ["elec_fan_install"]))
        self.assertEqual(self.worker.get(reverse("booking", args=[self.id])).json()["status"], "completed")  # same for both
        kinds = list(BookingEvent.objects.filter(booking_id=self.id).values_list("kind", flat=True))
        self.assertEqual((kinds.count("completion_requested"), kinds.count("completed")), (1, 1))
        self.assertIsNone(self.worker.get(reverse("booking", args=[self.id])).json()["address"])  # no longer needed
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.accepting_requests)
        self.assertEqual(Booking.objects.get(pk=self.id).accepted_terms["quantity"], 2)  # the snapshot is untouched

        # The slot is released and the worker can start another (non-overlapping or even overlapping-in-past) job.
        other = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        second = started(other, self.profile, at(2, 10))
        self.assertEqual(second.status, "in_progress")

    def test_a_second_start_is_blocked_while_awaiting_confirmation_or_disputed_even_after_the_planned_end(self):
        self.to_completion_requested()
        other = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        quote = ready_quote(make_invitation(other, self.profile), start=at(2, 10))
        second, _ = services.accept_quote(other, invitation_id=quote.invitation_id, quote_id=quote.id, version=1, key=uuid.uuid4())
        services.mark_arrived(self.profile.user, second.pk)
        code, _ = services.issue_code(other, second.pk)
        after_end = self.booking.end_at + timedelta(hours=3)
        with mock.patch("django.utils.timezone.now", return_value=after_end):
            refused = self.post(self.worker, "booking-start", {"code": code}, booking_id=second.pk)
        self.assertEqual(refused.json()["error"]["code"], "worker_has_job_in_progress")
        self.post(self.customer, "booking-raise-issue", {"reason": "not_finished", "note": "ایک پنکھا ابھی نہیں چلا"})
        self.assertEqual(self.post(self.worker, "booking-start", {"code": code}, booking_id=second.pk).json()["error"]["code"],
                         "worker_has_job_in_progress")
        # Overlapping acceptance is also still refused: the disputed booking keeps its reservation.
        third = ready_quote(make_invitation(other, self.profile), start=at(1, 18))
        self.assertEqual(client_for(other).post(reverse("bookings"), accept_body(third), format="json").json()["error"]["code"],
                         "schedule_conflict")
        services.staff_resolve(staff_with("resolve_dispute"), self.id, outcome="close", reason="Both agreed to stop here.")
        self.assertEqual(self.post(self.worker, "booking-start", {"code": code}, booking_id=second.pk).status_code, 200)

    def test_an_open_change_must_be_decided_before_completion_and_terms_freeze_afterwards(self):
        booking = self.worker.get(reverse("booking", args=[self.id])).json()
        terms = {name: booking["terms"][name] for name in services.TERM_FIELDS}
        terms.update(materials=terms["materials"] or "", quantity=3, note="تیسرا پنکھا")
        change = self.post(self.worker, "booking-changes", terms).json()["changes"][0]
        blocked = self.post(self.worker, "booking-request-completion")
        self.assertEqual((blocked.status_code, blocked.json()["error"]["code"]), (409, "change_open"))
        self.assertTrue(self.worker.get(reverse("booking", args=[self.id])).json()["actions"]["completion_blocked_by_change"])
        self.worker.post(reverse("booking-change-withdraw", args=[self.id, change["id"]]))
        self.to_completion_requested()
        frozen = self.post(self.customer, "booking-changes", {**terms, "note": "اور ایک"})
        self.assertEqual(frozen.json()["error"]["code"], "booking_state_conflict")

    def test_dispute_then_staff_return_to_work_then_close_without_completion(self):
        self.to_completion_requested()
        self.assertEqual(self.post(self.customer, "booking-raise-issue", {"reason": "not_finished"}).status_code, 400)
        disputed = self.post(self.customer, "booking-raise-issue", {"reason": "not_finished", "note": "ایک پنکھا نہیں چلا"}).json()
        self.assertEqual((disputed["status"], disputed["dispute_reason"]), ("disputed", "not_finished"))
        self.assertEqual(self.post(self.customer, "booking-confirm-completion").json()["error"]["code"], "booking_state_conflict")
        with self.assertRaises(ApiError):
            services.staff_resolve(staff_with(), self.id, outcome="return_to_work", reason="Needs one more visit.")
        staff = staff_with("resolve_dispute")
        back = services.staff_resolve(staff, self.id, outcome="return_to_work", reason="Worker will fix the third fan.")
        self.assertEqual(back.status, "in_progress")
        self.to_completion_requested()
        self.post(self.customer, "booking-raise-issue", {"reason": "not_as_agreed", "note": "پھر بھی ٹھیک نہیں"})
        closed = services.staff_resolve(staff, self.id, outcome="close", reason="Closed after talking to both people.")
        self.assertEqual(closed.status, "closed")
        view = self.customer.get(reverse("booking", args=[self.id])).json()
        self.assertEqual((view["staff_outcome"], view["actions"]["review"]), ("close", False))
        refused = self.post(self.customer, "booking-review", {"rating": 1, "text": "x"})
        self.assertEqual((refused.status_code, refused.json()["error"]["code"]), (409, "review_not_allowed"))
        self.booking.invitation.refresh_from_db()
        self.assertEqual(self.booking.invitation.status, "cancelled")  # conversation read-only, quote not reusable
        self.assertEqual(worker_stats([self.profile.pk])[str(self.profile.pk)].completed_jobs, 0)  # no credit


class AdminActionTests(CompletionTestCase):
    def test_dispute_outcome_requires_the_permission(self):
        self.to_completion_requested()
        self.post(self.customer, "booking-raise-issue", {"reason": "damage", "note": "دیوار خراب ہوئی"})
        url = reverse("admin:bookings_booking_resolve", args=[self.id])
        anonymous = self.client.get(url)
        self.assertEqual(anonymous.status_code, 302)
        self.client.force_login(staff_with())
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(staff_with("resolve_dispute", "view_booking"))
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {"outcome": "close", "reason": "Recorded after a call with both."})
        self.assertEqual(response.status_code, 302)
        booking = Booking.objects.get(pk=self.id)
        self.assertEqual((booking.status, booking.staff_outcome, booking.staff_reason), ("closed", "close", "Recorded after a call with both."))
        self.assertTrue(BookingEvent.objects.filter(booking=booking, kind="staff_resolved", actor_role="staff").exists())

    def test_hiding_a_review_requires_the_permission_and_keeps_the_text(self):
        self.complete()
        review = self.post(self.customer, "booking-review", {"rating": 1, "text": "abusive words"}).json()
        url = reverse("admin:reviews_review_hide", args=[review["id"]])
        self.client.force_login(staff_with())
        self.assertEqual(self.client.post(url, {"reason": "Abusive language"}).status_code, 403)
        self.client.force_login(staff_with("hide_review", "view_review"))
        self.assertEqual(self.client.post(url, {"reason": "Abusive language"}).status_code, 302)
        stored = Review.objects.get(pk=review["id"])
        self.assertEqual((stored.text, stored.hidden_reason), ("abusive words", "Abusive language"))
        self.assertIsNotNone(stored.hidden_at)


class ReviewTests(CompletionTestCase):
    def test_one_review_only_after_confirmed_completion_and_only_by_its_customer(self):
        self.assertEqual(self.post(self.customer, "booking-review", {"rating": 5}).json()["error"]["code"], "review_not_allowed")
        self.complete()
        self.assertEqual(self.post(self.worker, "booking-review", {"rating": 5}).status_code, 403)
        stranger = client_for(User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER))
        self.assertEqual(self.post(stranger, "booking-review", {"rating": 5}).status_code, 404)
        self.assertEqual(self.post(self.customer, "booking-review", {"rating": 6}).status_code, 400)
        first = self.post(self.customer, "booking-review", {"rating": 5, "text": "بہت اچھا کام"})
        self.assertEqual((first.status_code, first.json()["created"], first.json()["services"]), (201, True, ["elec_fan_install"]))
        again = self.post(self.customer, "booking-review", {"rating": 1, "text": "changed my mind"})
        self.assertEqual((again.status_code, again.json()["id"], again.json()["rating"]), (200, first.json()["id"], 5))
        self.assertEqual(Review.objects.count(), 1)
        worker_view = self.worker.get(reverse("booking", args=[self.id])).json()
        self.assertEqual(worker_view["review"]["text"], "بہت اچھا کام")
        self.assertNotIn("interpreted_text", worker_view["review"])
        self.assertFalse(worker_view["actions"]["review"])

    def test_cancelled_bookings_cannot_be_reviewed(self):
        other = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        quote = ready_quote(make_invitation(other, self.profile), start=at(3, 10))
        booking, _ = services.accept_quote(other, invitation_id=quote.invitation_id, quote_id=quote.id, version=1, key=uuid.uuid4())
        services.cancel(other, booking.pk, reason="changed_plans", note="")
        response = client_for(other).post(reverse("booking-review", args=[booking.pk]), {"rating": 4}, format="json")
        self.assertEqual(response.json()["error"]["code"], "review_not_allowed")

    def test_a_spoken_review_keeps_the_proposal_and_the_approved_text(self):
        self.complete()
        clip = self.customer.post(reverse("audio-clips"), {"file": SimpleUploadedFile("r.wav", make_wav(2), content_type="audio/wav"),
                                                            "purpose": "review", "source": "recording"}, format="multipart").json()
        transcription = self.customer.post(reverse("audio-transcribe"), {"clip_id": clip["id"], "language": "ur"}, format="json").json()
        self.assertIn("پنکھے", transcription["text"])
        approved = transcription["text"] + " شکریہ۔"
        review = self.post(self.customer, "booking-review", {"rating": 4, "text": approved, "audio_clip_id": clip["id"],
                                                            "transcription_id": transcription["id"]}).json()
        self.assertEqual((review["source"], review["text"], review["interpreted_text"]), ("voice", approved, transcription["text"]))
        other_clip_user = client_for(User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER))
        self.assertEqual(other_clip_user.get(f"/api/v1/audio/clips/{clip['id']}/content/").status_code, 404)

    def test_worker_feedback_shows_jobs_and_visible_reviews_without_private_details(self):
        self.complete()
        self.post(self.customer, "booking-review", {"rating": 4, "text": "صاف ستھرا کام"})
        feedback = self.worker.get(reverse("worker-feedback")).json()
        self.assertEqual((feedback["completed_jobs"], feedback["review_count"], feedback["average_rating"]), (1, 1, "4.0"))
        self.assertEqual(feedback["jobs"][0]["review"]["text"], "صاف ستھرا کام")
        body = json.dumps(feedback, ensure_ascii=False)
        for private in ("House 5", "Ring twice", "phone", "cnic"):
            self.assertNotIn(private, body)
        self.assertEqual(self.customer.get(reverse("worker-feedback")).status_code, 403)
        from apps.reviews.services import hide_review
        hide_review(staff_with("hide_review"), feedback["jobs"][0]["review"]["id"], "Test hiding")
        hidden = self.worker.get(reverse("worker-feedback")).json()
        self.assertEqual((hidden["completed_jobs"], hidden["review_count"], hidden["average_rating"]), (1, 0, None))
        self.assertIsNone(hidden["jobs"][0]["review"])
        self.assertIsNone(self.worker.get(reverse("booking", args=[self.id])).json()["review"])
        self.assertTrue(self.customer.get(reverse("booking", args=[self.id])).json()["review"]["hidden"])


class RecommendationTests(CompletionTestCase):
    def test_completed_work_and_visible_reviews_refine_the_ranking(self):
        newcomer = make_worker()  # same trade, area and speciality; no history
        job_customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        summary = matching_summary(make_invitation(job_customer, newcomer).job)
        cards = {str(m.profile.id): m for m in recommend(summary)}
        self.assertTrue(cards[str(self.profile.id)].stats.completed_jobs == 0)

        self.complete()
        self.post(self.customer, "booking-review", {"rating": 5, "text": "بہترین"})
        ranked = recommend(summary)
        first = ranked[0]
        self.assertEqual(first.profile.id, self.profile.id)  # relevant completed work ranks first among equals
        from apps.invitations.matching import worker_card
        card = worker_card(first)
        self.assertEqual((card["is_new"], card["history"]["relevant_jobs"], card["history"]["average_rating"],
                          card["history"]["review_count"]), (False, 1, "5.0", 1))
        self.assertIn({"code": "completed_jobs", "count": 1, "services": ["elec_fan_install"]}, card["reasons"])
        newcomer_card = worker_card(next(m for m in ranked if m.profile.id == newcomer.id))
        self.assertEqual((newcomer_card["is_new"], newcomer_card["history"]["average_rating"]), (True, None))  # no rating, not zero

        from apps.reviews.services import hide_review
        hide_review(staff_with("hide_review"), Review.objects.get().pk, "Test")
        hidden_card = worker_card(next(m for m in recommend(summary) if m.profile.id == self.profile.id))
        self.assertEqual((hidden_card["history"]["review_count"], hidden_card["history"]["average_rating"],
                          hidden_card["history"]["relevant_jobs"]), (0, None, 1))

    def test_a_low_rating_does_not_rank_above_an_unrated_worker_with_the_same_experience(self):
        self.complete()
        self.post(self.customer, "booking-review", {"rating": 1, "text": "خراب"})
        other_worker = make_worker()
        other_customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        booking = started(other_customer, other_worker, at(2, 10))
        services.request_completion(other_worker.user, booking.pk)
        services.confirm_completion(other_customer, booking.pk)  # same experience, no review
        summary = matching_summary(make_invitation(other_customer, other_worker).job)
        order = [m.profile.id for m in recommend(summary) if m.profile.id in (self.profile.id, other_worker.id)]
        self.assertEqual(order, [other_worker.id, self.profile.id])

    def test_stats_use_two_grouped_queries_for_any_number_of_workers(self):
        workers = [make_worker() for _ in range(4)] + [self.profile]
        self.complete()
        with self.assertNumQueries(2):
            stats = worker_stats([w.pk for w in workers], ["elec_fan_install"])
        self.assertEqual(stats[str(self.profile.pk)].relevant_jobs, 1)
        unrelated = worker_stats([self.profile.pk], ["elec_wiring_repair"])[str(self.profile.pk)]
        self.assertEqual((unrelated.completed_jobs, unrelated.relevant_jobs), (1, 0))  # no credit for other services


class CompletionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        seed()

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

    def test_confirm_against_dispute_and_duplicate_reviews(self):
        profile = make_worker()
        for day in (1, 2, 3):
            customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
            booking = started(customer, profile, at(day, 17))
            services.request_completion(profile.user, booking.pk)
            outcomes = self._race(lambda: services.confirm_completion(customer, booking.pk).status,
                                  lambda: services.raise_issue(customer, booking.pk, reason="other", note="race test").status)
            final = Booking.objects.get(pk=booking.pk).status
            self.assertIn(final, ("completed", "disputed"))
            self.assertIn("booking_state_conflict", outcomes)  # exactly one action won
            self.assertIn(final, outcomes)
            if final == "disputed":
                services.staff_resolve(User.objects.create_superuser(next_phone(), PASSWORD), booking.pk, outcome="close",
                                       reason="race cleanup")
            else:
                reviews = self._race(lambda: submit_review(customer, booking.pk, rating=5, text="a")[1],
                                     lambda: submit_review(customer, booking.pk, rating=4, text="b")[1])
                self.assertEqual(sorted(reviews), [False, True])
                self.assertEqual(Review.objects.filter(booking=booking).count(), 1)

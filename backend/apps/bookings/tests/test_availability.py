"""Expected availability on recommendation cards (informative only; the booking checks stay authoritative)."""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from apps.bookings import availability, services
from apps.bookings.models import Booking
from apps.invitations.tests.helpers import PASSWORD, User, client_for, make_worker, next_phone

from .test_bookings import BookingTestCase, at, make_invitation, ready_quote

KARACHI = ZoneInfo("Asia/Karachi")


def k(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2030, 1, day, hour, minute, tzinfo=KARACHI)


NOW = k(9, 12)
WINDOW = (k(10, 16), k(10, 20))  # the customer's requested 4–8 PM on 10 January


def utc(value: datetime) -> str:
    return value.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def set_status(booking, status):
    """Move a test booking to ``status`` with the times the database requires for it."""
    now = timezone.now()
    values = {"status": status}
    if status == Booking.Status.CANCELLED:
        values.update(cancelled_at=now, cancel_reason="other")
    elif status == Booking.Status.COMPLETED:
        values.update(arrived_at=now, started_at=now, completion_requested_at=now, completed_at=now)
    elif status == Booking.Status.CLOSED:
        values.update(closed_at=now, staff_reason="Test outcome")
    Booking.objects.filter(pk=booking.pk).update(**values)


class StatusRuleTests(SimpleTestCase):
    def status(self, bookings, window=WINDOW, now=NOW):
        return availability.status_for(bookings, *window, now)

    def test_no_reserving_booking_in_the_window_is_available(self):
        self.assertEqual(self.status([]), {"status": "available", "at": None})
        # Back-to-back is free: [2 PM, 4 PM) ends exactly when the window starts, [8 PM, 9 PM) starts when it ends.
        self.assertEqual(self.status([(k(10, 14), k(10, 16), "confirmed"), (k(10, 20), k(10, 21), "confirmed")])["status"], "available")

    def test_a_booking_covering_the_whole_window_gives_the_next_free_time(self):
        self.assertEqual(self.status([(k(10, 15), k(10, 21), "confirmed")]), {"status": "busy", "at": utc(k(10, 21))})

    def test_adjacent_reservations_are_followed(self):
        # 4–6 PM then 6–8 PM: free at 8 PM, the end of the window.
        chain = [(k(10, 16), k(10, 18), "confirmed"), (k(10, 18), k(10, 20), "confirmed")]
        self.assertEqual(self.status(chain), {"status": "busy", "at": utc(k(10, 20))})
        # … and a third one right after the window: free at 9 PM.
        self.assertEqual(self.status([*chain, (k(10, 20), k(10, 21), "confirmed")]), {"status": "busy", "at": utc(k(10, 21))})

    def test_a_partial_overlap_shows_when_the_worker_becomes_free_within_the_window(self):
        self.assertEqual(self.status([(k(10, 15), k(10, 18), "confirmed")]), {"status": "partly_available", "at": utc(k(10, 18))})
        # Free at the start, booked later in the window: free from the start.
        self.assertEqual(self.status([(k(10, 18), k(10, 22), "confirmed")]), {"status": "partly_available", "at": utc(k(10, 16))})

    def test_a_job_still_open_after_its_planned_end_makes_the_next_time_uncertain(self):
        overdue = [(k(9, 9), k(9, 11), "in_progress")]  # planned to end at 11 AM; it is now noon
        self.assertEqual(self.status(overdue), {"status": "uncertain", "at": None})
        self.assertEqual(self.status([(k(9, 9), k(9, 11), "completion_requested")])["status"], "uncertain")
        # A booking that never started is not running: its past time no longer holds anything.
        self.assertEqual(self.status([(k(9, 9), k(9, 11), "confirmed")])["status"], "available")

    def test_never_a_time_in_the_past(self):
        # The window has already begun (5 PM) and a booking runs until 6 PM: free from 6 PM, not from 4 PM.
        result = self.status([(k(10, 15), k(10, 18), "in_progress")], now=k(10, 17))
        self.assertEqual(result, {"status": "partly_available", "at": utc(k(10, 18))})


class AvailabilityQueryTests(BookingTestCase):
    """Real bookings for one worker; only reserving statuses count, in one batched query."""

    def book(self, start, hours=2):
        customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        invitation = make_invitation(customer, self.profile)
        quote = ready_quote(invitation, start=start, hours=hours)
        booking, _ = services.accept_quote(customer, invitation_id=invitation.id, quote_id=quote.id, version=quote.version, key=uuid.uuid4())
        return booking

    def test_cancelled_completed_and_closed_bookings_are_ignored(self):
        start = at(3, 16)
        for status in (Booking.Status.CANCELLED, Booking.Status.COMPLETED, Booking.Status.CLOSED):
            set_status(self.book(start), status)
        result = availability.for_workers([self.profile.pk], start, start + timedelta(hours=4))
        self.assertEqual(result[str(self.profile.pk)], {"status": "available", "at": None})

    def test_reserving_bookings_of_many_workers_in_one_query(self):
        start = at(3, 16)
        self.book(start)                                   # 4–6 PM
        self.book(start + timedelta(hours=2))              # 6–8 PM, adjacent
        other = make_worker()
        with self.assertNumQueries(1):
            result = availability.for_workers([self.profile.pk, other.pk], start, start + timedelta(hours=3))
        self.assertEqual(result[str(self.profile.pk)], {"status": "busy", "at": utc(start + timedelta(hours=4))})
        self.assertEqual(result[str(other.pk)]["status"], "available")


class RecommendationAvailabilityTests(BookingTestCase):
    def test_a_busy_worker_stays_listed_with_only_a_status_and_a_time(self):
        # Another customer books the worker over the whole of tomorrow 5–7 PM (the request's window in make_confirmed_job).
        self.booked()
        customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        invitation = make_invitation(customer, self.profile)
        response = client_for(customer).get(reverse("job-recommendations", args=[invitation.job_id]))
        self.assertEqual(response.status_code, 200, response.content)
        card = next(c for c in response.json()["workers"] if c["worker_id"] == str(self.profile.pk))
        self.assertEqual(card["availability"]["status"], "busy")
        self.assertEqual(set(card["availability"]), {"status", "at"})  # no booking id, address, job or customer
        self.assertEqual(card["availability"]["at"], utc(self.quote.end_at))
        self.assertNotIn("House 5", response.content.decode())

    def test_a_stale_estimate_cannot_bypass_the_booking_conflict_check(self):
        customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        invitation = make_invitation(customer, self.profile)
        listed = client_for(customer).get(reverse("job-recommendations", args=[invitation.job_id])).json()
        card = next(c for c in listed["workers"] if c["worker_id"] == str(self.profile.pk))
        self.assertEqual(card["availability"]["status"], "available")  # true when it was shown …
        self.booked()                                                  # … then another customer books that time
        quote = ready_quote(invitation, start=self.quote.start_at)
        response = client_for(customer).post(reverse("bookings"), {
            "invitation_id": str(invitation.id), "quote_id": str(quote.id), "version": quote.version,
            "idempotency_key": str(uuid.uuid4())}, format="json")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"]["code"], "schedule_conflict")
        self.assertEqual(Booking.objects.filter(worker_profile=self.profile).exclude(status=Booking.Status.CANCELLED).count(), 1)

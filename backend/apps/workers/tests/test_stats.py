"""The worker's own Performance totals (GET /workers/me/stats/): counted on the server, owner-scoped."""

import uuid

from django.urls import reverse
from django.utils import timezone

from apps.bookings import services
from apps.bookings.models import Booking
from apps.bookings.tests.test_availability import set_status
from apps.bookings.tests.test_bookings import BookingTestCase, at, make_invitation, ready_quote
from apps.invitations.models import Invitation
from apps.invitations.tests.helpers import PASSWORD, User, client_for, make_worker, next_phone
from apps.reviews.models import Review


class WorkerStatsTests(BookingTestCase):
    def completed_booking(self, profile, day):
        customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        invitation = make_invitation(customer, profile)
        quote = ready_quote(invitation, start=at(day, 10))
        booking, _ = services.accept_quote(customer, invitation_id=invitation.id, quote_id=quote.id, version=1, key=uuid.uuid4())
        set_status(booking, Booking.Status.COMPLETED)
        return booking

    def review(self, booking, rating, hidden=False):
        return Review.objects.create(booking=booking, customer=booking.customer, worker_profile=booking.worker_profile, rating=rating,
                                     hidden_at=timezone.now() if hidden else None, hidden_reason="Abusive" if hidden else "")

    def stats(self, client=None):
        response = (client or self.worker).get(reverse("worker-stats"))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_no_reviews_yet(self):
        data = self.stats()
        self.assertEqual(data["invitations_received"], 1)  # the invitation made in setUp
        self.assertEqual((data["completed_jobs"], data["review_count"], data["average_rating"]), (0, 0, None))
        self.assertEqual(data["rating_distribution"], [{"stars": s, "count": 0} for s in (5, 4, 3, 2, 1)])

    def test_lifetime_totals_from_real_records(self):
        # Invitations in every status count; completed bookings and only VISIBLE reviews.
        Invitation.objects.filter(pk=self.invitation.pk).update(status=Invitation.Status.DECLINED, closed_at=timezone.now())
        five, four, hidden = (self.completed_booking(self.profile, day) for day in (2, 3, 4))
        self.review(five, 5)
        self.review(four, 4)
        self.review(hidden, 1, hidden=True)
        # Another worker's records never count here.
        other = make_worker()
        self.review(self.completed_booking(other, 5), 1)

        data = self.stats()
        self.assertEqual(data["invitations_received"], 4)   # declined + three that became bookings
        self.assertEqual(data["completed_jobs"], 3)
        self.assertEqual((data["review_count"], data["average_rating"]), (2, "4.5"))
        self.assertEqual({row["stars"]: row["count"] for row in data["rating_distribution"]}, {5: 1, 4: 1, 3: 0, 2: 0, 1: 0})
        # The same aggregates as the existing feedback endpoint.
        feedback = self.worker.get(reverse("worker-feedback")).json()
        self.assertEqual((feedback["completed_jobs"], feedback["review_count"], feedback["average_rating"]), (3, 2, "4.5"))

    def test_more_invitations_than_one_page(self):
        customer = User.objects.create_user(next_phone(), PASSWORD, role=User.Role.CUSTOMER)
        for _ in range(55):  # the inbox lists 50 per page; the total is counted on the server
            make_invitation(customer, self.profile)
        self.assertEqual(self.stats()["invitations_received"], 56)

    def test_only_workers(self):
        self.assertEqual(self.customer.get(reverse("worker-stats")).status_code, 403)
        self.assertIn(client_for(make_worker().user).get(reverse("worker-stats")).json()["invitations_received"], (0,))

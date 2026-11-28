"""Reviews and work-history aggregates (M9: REV-01, REV-02, REC-04).

Aggregates are always computed from eligible records (customer-confirmed ``completed`` bookings and their
visible reviews), never from editable profile numbers, and with grouped queries (one per measure, not one per
worker).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ErrorDetail, NotFound, ValidationError

from apps.bookings import errors as booking_errors
from apps.bookings.models import Booking, BookingEvent
from apps.bookings.services import participant_booking
from apps.core.api.exceptions import ApiError
from apps.voice.models import AudioClip, Purpose, Transcription

from .models import Review

logger = logging.getLogger(__name__)

# Smoothing for ranking only: a rating is pulled towards a neutral 3.0 as if it had PRIOR_COUNT extra 3-star
# reviews. An unrated worker ranks as neutral (not zero), and one 5-star review does not beat a long record.
PRIOR_RATING = Decimal("3")
PRIOR_COUNT = 2


class ReviewNotAllowed(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "review_not_allowed"
    default_detail = "Only the customer can review, and only after confirming completion."


# --- Aggregates -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkerStats:
    completed_jobs: int = 0          # customer-confirmed completed bookings
    relevant_jobs: int = 0           # … of which at least one confirmed service is among the requested ones
    review_count: int = 0            # visible reviews
    rating_sum: int = 0

    @property
    def average(self) -> Decimal | None:
        """The displayed average (one decimal). None when there are no visible reviews — never zero."""
        if not self.review_count:
            return None
        return (Decimal(self.rating_sum) / self.review_count).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def ranking_rating(self) -> Decimal:
        return (Decimal(self.rating_sum) + PRIOR_RATING * PRIOR_COUNT) / (self.review_count + PRIOR_COUNT)

    def as_dict(self) -> dict:
        return {"completed_jobs": self.completed_jobs, "relevant_jobs": self.relevant_jobs,
                "review_count": self.review_count, "average_rating": str(self.average) if self.average is not None else None}


def visible_reviews():
    return Review.objects.filter(hidden_at__isnull=True, booking__status=Booking.Status.COMPLETED)


def worker_stats(profile_ids, requested_services=()) -> dict[str, WorkerStats]:
    """Stats for many workers in two grouped queries."""
    ids = [str(pk) for pk in profile_ids]
    if not ids:
        return {}
    requested = list(requested_services)
    jobs = (
        Booking.objects.filter(worker_profile_id__in=ids, status=Booking.Status.COMPLETED)
        .values("worker_profile_id")
        .annotate(total=Count("id", distinct=True),
                  relevant=Count("id", filter=Q(completed_services__code__in=requested), distinct=True))
    )
    reviews = (
        visible_reviews().filter(worker_profile_id__in=ids).values("worker_profile_id")
        .annotate(n=Count("id"), total=Sum("rating"))
    )
    found: dict[str, dict] = {pk: {} for pk in ids}
    for row in jobs:
        found[str(row["worker_profile_id"])].update(completed_jobs=row["total"], relevant_jobs=row["relevant"] if requested else 0)
    for row in reviews:
        found[str(row["worker_profile_id"])].update(review_count=row["n"], rating_sum=row["total"] or 0)
    return {pk: WorkerStats(**values) for pk, values in found.items()}


def rating_distribution(profile_id) -> dict[int, int]:
    """Visible reviews of one worker per star rating (1–5), in one grouped query. Every rating is present (0 if none)."""
    rows = visible_reviews().filter(worker_profile_id=profile_id).values("rating").annotate(n=Count("id"))
    found = {row["rating"]: row["n"] for row in rows}
    return {stars: found.get(stars, 0) for stars in range(1, 6)}


# --- Payloads ---------------------------------------------------------------------------------------------------


def review_payload(review: Review, role: str) -> dict:
    payload = {
        "id": str(review.id), "rating": review.rating, "text": review.text, "source": review.source,
        "services": review.services, "created_at": review.created_at.isoformat().replace("+00:00", "Z"),
        "hidden": review.hidden_at is not None,
    }
    if role == "customer":
        payload["interpreted_text"] = review.interpreted_text or None  # the author's own automatic proposal
    return payload


# --- Submission -------------------------------------------------------------------------------------------------


def submit_review(user, booking_id, *, rating: int, text: str, audio_clip_id=None, transcription_id=None) -> tuple[Review, bool]:
    """One review per booking. A repeat submission returns the stored review (``created`` False)."""
    booking, role = participant_booking(user, booking_id)
    if role != "customer":
        raise booking_errors.NotYourAction()
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        existing = booking.reviews.first()
        if existing is not None:
            return existing, False
        if booking.status != Booking.Status.COMPLETED:  # cancelled, disputed, closed by staff, not yet confirmed …
            raise ReviewNotAllowed(details={"status": booking.status})
        clip, interpreted = None, ""
        if audio_clip_id:
            clip = AudioClip.objects.filter(pk=audio_clip_id, owner=user, purpose=Purpose.REVIEW).first()
            if clip is None or Review.objects.filter(audio_clip=clip).exists():
                raise ValidationError({"audio_clip_id": [ErrorDetail("Recording not found.", code="not_found")]})
            if transcription_id:
                transcription = Transcription.objects.filter(pk=transcription_id, clip=clip).first()
                if transcription is None:
                    raise ValidationError({"transcription_id": [ErrorDetail("Not found.", code="not_found")]})
                interpreted = transcription.text
        try:
            with transaction.atomic():
                review = Review.objects.create(
                    booking=booking, customer=user, worker_profile_id=booking.worker_profile_id, rating=rating,
                    text=text, source=Review.Source.VOICE if clip else Review.Source.TYPED, audio_clip=clip,
                    interpreted_text=interpreted, services=sorted(booking.completed_services.values_list("code", flat=True)),
                )
        except IntegrityError:  # backstop: review_one_per_booking
            return Review.objects.get(booking=booking), False
        BookingEvent.objects.create(booking=booking, kind=BookingEvent.Kind.REVIEWED, from_status=booking.status,
                                    to_status=booking.status, actor=user, actor_role=role, data={"rating": rating})
    logger.info("Review submitted.")
    return review, True


def hide_review(staff_user, review_id, reason: str) -> Review:
    """Django Admin only (permission reviews.hide_review). The original text is kept; the reason is audited."""
    if not (staff_user.is_active and staff_user.is_staff and staff_user.has_perm("reviews.hide_review")):
        raise booking_errors.NotYourAction()
    reason = reason.strip()
    if len(reason) < 3:
        raise ValidationError({"reason": [ErrorDetail("Give the reason for hiding.", code="required")]})
    with transaction.atomic():
        review = Review.objects.select_for_update().filter(pk=review_id).first()
        if review is None:
            raise NotFound()
        if review.hidden_at is None:
            review.hidden_at, review.hidden_by, review.hidden_reason = timezone.now(), staff_user, reason
            review.save(update_fields=["hidden_at", "hidden_by", "hidden_reason"])
            logger.info("Review hidden by staff.")
    return review


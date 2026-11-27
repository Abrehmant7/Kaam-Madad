"""One customer review per completed booking (M9: REV-01, REV-02).

- Only the booking's customer, only after THEY confirmed completion (status ``completed``; a booking staff
  closed without confirmed completion never qualifies). ``review_one_per_booking`` enforces one per booking.
- ``services`` are the booked catalog services confirmed as completed (copied from the booking), never tags
  inferred from the text or the worker's whole profile.
- A spoken review keeps the original audio clip and the transcription proposal; ``text`` is the wording the
  customer approved. Staff may HIDE an abusive review with a reason (audited); the original text is never
  rewritten. Hidden reviews are excluded from every displayed rating and count.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.bookings.models import Booking
from apps.workers.models import WorkerProfile


class Review(models.Model):
    class Source(models.TextChoices):
        TYPED = "typed", _("Typed")
        VOICE = "voice", _("Spoken, text approved by the customer")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="reviews")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    worker_profile = models.ForeignKey(WorkerProfile, on_delete=models.PROTECT, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    text = models.TextField(blank=True, default="", help_text=_("Exactly what the customer approved."))
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.TYPED)
    audio_clip = models.ForeignKey("voice.AudioClip", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    interpreted_text = models.TextField(blank=True, default="", help_text=_("Automatic proposal from the recording."))
    services = models.JSONField(default=list, help_text=_("Booked services confirmed as completed (catalog codes)."))
    created_at = models.DateTimeField(default=timezone.now)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    hidden_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        permissions = [("hide_review", "Can hide an abusive review (with a reason)")]
        indexes = [models.Index(fields=["worker_profile", "hidden_at"], name="review_worker_visible_idx")]
        constraints = [
            models.UniqueConstraint(fields=["booking"], name="review_one_per_booking"),
            models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="review_rating_1_to_5"),
            models.CheckConstraint(
                condition=Q(hidden_at__isnull=True, hidden_reason="") | (Q(hidden_at__isnull=False) & ~Q(hidden_reason="")),
                name="review_hidden_has_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"Review {str(self.id)[:8]} · {self.rating}/5{' (hidden)' if self.hidden_at else ''}"

"""Customer job requests (M5: JOB-01 to JOB-04).

- ``JobRequest`` is owned by one customer. It keeps the ORIGINAL input (typed text or the
  untouched transcript, with an owned reference to the audio clip / transcription /
  interpretation) separately from the customer-confirmed description and choices.
- Status: ``draft`` (saved, resumable, editable) → ``confirmed`` (validated, read-only in M5).
  Confirmation saves the request; it does not invite a worker or reserve a time (M6+).
- The preferred window is stored as timezone-aware UTC timestamps; the UI shows Asia/Karachi.
- ``address_private`` and ``access_notes`` are private to the customer: they never go to speech
  synthesis, AI interpretation or (later) matching summaries — see ``apps.jobs.summary``.
- ``budget_pkr`` is the customer's own preference, not a quote.
- ``JobPhoto``: up to five private reference images per request (re-encoded without metadata).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Area, City, ServiceTag, Trade


def photo_upload_path(instance, filename: str) -> str:
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(instance.mime_type, "")
    return f"job-photos/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{extension}"


class JobRequest(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        CONFIRMED = "confirmed", _("Confirmed (saved; no worker invited yet)")

    class SourceKind(models.TextChoices):
        TEXT = "text", _("Typed")
        VOICE = "voice", _("Voice")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="job_requests")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    # Original input — set once, never edited.
    source_kind = models.CharField(max_length=8, choices=SourceKind.choices)
    source_language = models.CharField(max_length=8, blank=True, default="")
    original_text = models.TextField(blank=True, default="", help_text=_("Typed text or the untouched transcript."))
    audio_clip = models.ForeignKey("voice.AudioClip", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    transcription = models.ForeignKey("voice.Transcription", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    interpretation = models.ForeignKey(
        "voice.Interpretation", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text=_("AI suggestions used to pre-fill the draft (editable)."),
    )

    # Customer-confirmed details.
    description = models.TextField(blank=True, default="")
    trade = models.ForeignKey(Trade, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    services = models.ManyToManyField(ServiceTag, blank=True, related_name="job_requests")
    services_excluded = models.ManyToManyField(ServiceTag, blank=True, related_name="+")
    city = models.ForeignKey(City, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.PROTECT, related_name="job_requests")
    preferred_time_text = models.CharField(
        max_length=120, blank=True, default="", help_text=_("The time as the customer said it, e.g. 'kal shaam'."),
    )
    window_start = models.DateTimeField(null=True, blank=True)
    window_end = models.DateTimeField(null=True, blank=True)
    address_private = models.TextField(blank=True, default="", help_text=_("Exact address. Private to the customer."))
    access_notes = models.TextField(blank=True, default="", help_text=_("Access instructions. Private."))
    budget_pkr = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_("The customer's preference in PKR. Not a quote."),
    )

    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["customer", "status", "-updated_at"], name="jobs_customer_status_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(status="draft", confirmed_at__isnull=True)
                | Q(status="confirmed", confirmed_at__isnull=False, trade__isnull=False, area__isnull=False,
                    city__isnull=False, window_start__isnull=False, window_end__isnull=False),
                name="jobs_confirmed_has_required_fields",
            ),
            models.CheckConstraint(
                condition=Q(window_start__isnull=True) | Q(window_end__isnull=True) | Q(window_end__gt=F("window_start")),
                name="jobs_window_end_after_start",
            ),
            models.CheckConstraint(
                condition=Q(budget_pkr__isnull=True) | Q(budget_pkr__gte=0), name="jobs_budget_not_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"Job request {str(self.id)[:8]} · {self.get_status_display()}"


class JobPhoto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(JobRequest, on_delete=models.CASCADE, related_name="photos")
    file = models.FileField(upload_to=photo_upload_path, max_length=200)
    mime_type = models.CharField(max_length=32)
    size_bytes = models.PositiveIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Photo {str(self.id)[:8]} of {self.job_id}"

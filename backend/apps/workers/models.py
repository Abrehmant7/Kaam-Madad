"""Worker profile, identity verification and the demo identity registry (M4).

- ``WorkerProfile`` holds the worker's own declarations (WK-02, WK-03): trade, services
  offered / main specialities / services not offered, city and the service areas the worker
  is willing to travel to (WK-04 as amended: manual selection, no browser location).
  Completion is never stored as a flag: it is recomputed from the data by
  ``apps.workers.onboarding`` so that server-side validation decides it.
  ``accepting_requests`` is the worker's own preference, separate from completion and
  identity status (WK-05).
- ``IdentityVerification`` is one verification attempt, kept apart from the profile (ID-01,
  ID-02). It stores the method, status, timestamps and references, scan metadata (never the
  image: scans are processed in a temporary folder that is deleted), the OCR draft only until
  the worker submits, whether the worker corrected the name/number, and only a keyed digest +
  masked form of the confirmed CNIC number. Raw OCR text and full numbers are never stored
  after submission and never appear in status payloads, admin lists or logs.
- ``DemoIdentityRecord`` is the fictional registry used in demo deployments only.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Area, City, ServiceTag, Trade


class WorkerProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="worker_profile")
    trade = models.ForeignKey(Trade, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    services_offered = models.ManyToManyField(ServiceTag, blank=True, related_name="offered_in_profiles")
    primary_specialities = models.ManyToManyField(ServiceTag, blank=True, related_name="primary_in_profiles")
    services_not_offered = models.ManyToManyField(ServiceTag, blank=True, related_name="excluded_in_profiles")
    city = models.ForeignKey(City, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    service_areas = models.ManyToManyField(
        Area, blank=True, related_name="worker_profiles",
        help_text=_("Areas the worker is willing to travel to for jobs (not their current location)."),
    )
    accepting_requests = models.BooleanField(
        default=True, help_text=_("Worker's own choice to receive job requests. Separate from completion and identity."),
    )
    work_saved_at = models.DateTimeField(null=True, blank=True)
    areas_saved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("worker profile")

    def __str__(self) -> str:
        return f"Worker profile · {self.user}"


class IdentityVerification(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In progress (consent given, not yet checked)")
        NO_MATCH = "no_match", _("Not matched — worker may correct and retry")
        DEMO_APPROVED = "demo_approved", _("Demo approved (fictional record, demo deployments only)")
        PROVIDER_VERIFIED = "provider_verified", _("Provider verified (authorised provider)")
        MANUALLY_REVIEWED = "manually_reviewed", _("Manually reviewed by staff")
        REJECTED = "rejected", _("Rejected")
        EXPIRED = "expired", _("Expired")
        SUSPENDED = "suspended", _("Suspended")
        SUPERSEDED = "superseded", _("Replaced by a newer attempt")

    class Method(models.TextChoices):
        DEMO_REGISTRY = "demo_registry", _("Demo registry lookup (fictional records)")
        # Reserved: only with authorised access and a contract (ID-02). Not implemented.
        NADRA = "nadra", _("NADRA (authorised access)")
        MANUAL_REVIEW = "manual_review", _("Manual staff review")

    class OcrStatus(models.TextChoices):
        NOT_RUN = "", _("Not run")
        READ = "read", _("Name and number read")
        PARTIAL = "partial", _("Only one field read")
        UNREADABLE = "unreadable", _("Nothing read")
        FAILED = "failed", _("OCR error (setup or engine)")

    class RegistryOutcome(models.TextChoices):
        NOT_CHECKED = "", _("Not checked")
        MATCH = "match", _("Name and number match one record")
        NAME_MISMATCH = "name_mismatch", _("Number found, name differs")
        NO_RECORD = "no_record", _("No record for this number")

    CONSENT_VERSION = "2026-11-27"
    ACTIVE_STATUSES = {Status.IN_PROGRESS, Status.NO_MATCH}
    SCANNED_STATUSES = {OcrStatus.READ, OcrStatus.PARTIAL, OcrStatus.UNREADABLE}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="identity_verifications")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.IN_PROGRESS)
    method = models.CharField(max_length=24, choices=Method.choices, blank=True, default="")
    consent_given_at = models.DateTimeField()
    consent_version = models.CharField(max_length=16)

    # Scan metadata only — the image itself is never stored.
    scan_count = models.PositiveSmallIntegerField(default=0)
    scanned_at = models.DateTimeField(null=True, blank=True)
    scan_mime_type = models.CharField(max_length=32, blank=True, default="")
    scan_width = models.PositiveIntegerField(null=True, blank=True)
    scan_height = models.PositiveIntegerField(null=True, blank=True)
    scan_size_bytes = models.PositiveIntegerField(null=True, blank=True)

    ocr_status = models.CharField(max_length=16, choices=OcrStatus.choices, blank=True, default="")
    ocr_provider = models.CharField(max_length=32, blank=True, default="")
    ocr_engine = models.CharField(max_length=64, blank=True, default="")
    ocr_rotation = models.PositiveSmallIntegerField(default=0)
    ocr_failure_reason = models.CharField(max_length=64, blank=True, default="")
    # The original OCR draft, for the owner's review only; cleared when the worker submits.
    ocr_name_pending = models.CharField(max_length=80, blank=True, default="")
    ocr_number_pending = models.CharField(max_length=13, blank=True, default="")

    cnic_digest = models.CharField(max_length=64, blank=True, default="", help_text=_("Keyed digest, never the number."))
    cnic_masked = models.CharField(max_length=20, blank=True, default="")
    name_corrected = models.BooleanField(default=False, help_text=_("The submitted name differs from the scan."))
    number_corrected = models.BooleanField(default=False, help_text=_("The submitted number differs from the scan."))
    submitted_at = models.DateTimeField(null=True, blank=True)
    submission_count = models.PositiveSmallIntegerField(default=0)

    registry_outcome = models.CharField(max_length=16, choices=RegistryOutcome.choices, blank=True, default="")
    registry_provider = models.CharField(max_length=32, blank=True, default="")
    registry_reference = models.CharField(max_length=64, blank=True, default="")
    registry_simulated = models.BooleanField(default=False)
    registry_checked_at = models.DateTimeField(null=True, blank=True)

    decided_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    review_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("identity verification")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=~Q(status="superseded"), name="workers_one_current_verification",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["demo_approved", "provider_verified", "manually_reviewed"])
                | (Q(decided_at__isnull=False) & ~Q(method="")),
                name="workers_verified_has_method_and_time",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_status_display()} · {self.user}"


class DemoIdentityRecord(models.Model):
    """A FICTIONAL person in the demo registry. Identifiers are synthetic (00000-…); never real data."""

    reference = models.CharField(max_length=32, unique=True)
    full_name_en = models.CharField(max_length=120, help_text=_("Printed English name, as on the demo card."))
    full_name_ur = models.CharField(max_length=120)
    demo_address = models.CharField(
        max_length=200, blank=True, default="",
        help_text=_("Fictional address, shown as 'Demo address'. Not a service area."),
    )
    cnic_digest = models.CharField(max_length=64, unique=True)
    cnic_masked = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("demo identity record")
        ordering = ["reference"]

    def __str__(self) -> str:
        return f"{self.reference} · {self.full_name_en} (fictional)"

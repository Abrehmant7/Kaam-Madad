"""Targeted invitations (M6: JOB-05, JOB-06).

An ``Invitation`` links ONE confirmed ``JobRequest`` to ONE worker. Its UUID is stable and is the
identity the M7 conversation will hang off. States:

- ``active``    — sent and open (at most ONE per request: partial unique index, plus a row lock on
                  the request when sending, so concurrent sends cannot create two);
- ``declined``  — closed by the worker;
- ``withdrawn`` — closed by the customer.

Closed invitations are kept as history; inviting again (even the same worker) creates a NEW
invitation with a new ID. An invitation never reserves time or confirms a booking (M8).

``shared_summary`` stores exactly what was shared: ``apps.jobs.summary.matching_summary(job)`` at
send time (no exact address, access notes, photos, recordings, transcripts or customer identity).
"""

from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.jobs.models import JobRequest
from apps.workers.models import WorkerProfile


class Invitation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        DECLINED = "declined", _("Declined by the worker")
        WITHDRAWN = "withdrawn", _("Withdrawn by the customer")

    class DeclineReason(models.TextChoices):
        NOT_AVAILABLE = "not_available", _("Not available at that time")
        TOO_FAR = "too_far", _("Too far")
        NOT_MY_WORK = "not_my_work", _("Not my kind of work")
        OTHER = "other", _("Other")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(JobRequest, on_delete=models.PROTECT, related_name="invitations")
    worker_profile = models.ForeignKey(WorkerProfile, on_delete=models.PROTECT, related_name="invitations")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    shared_summary = models.JSONField(help_text=_("What was shared with the worker (matching_summary at send time)."))
    created_at = models.DateTimeField(default=timezone.now)
    seen_at = models.DateTimeField(null=True, blank=True, help_text=_("When the worker first opened it."))
    closed_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.CharField(max_length=16, choices=DeclineReason.choices, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["worker_profile", "status", "-created_at"], name="inv_worker_status_idx")]
        constraints = [
            # JOB-06: one active invitation per request, enforced by PostgreSQL.
            models.UniqueConstraint(fields=["job"], condition=Q(status="active"), name="inv_one_active_per_job"),
            models.CheckConstraint(
                condition=Q(status="active", closed_at__isnull=True) | (~Q(status="active") & Q(closed_at__isnull=False)),
                name="inv_closed_has_time",
            ),
            models.CheckConstraint(
                condition=Q(decline_reason="") | Q(status="declined"), name="inv_reason_only_when_declined",
            ),
        ]

    def __str__(self) -> str:
        return f"Invitation {str(self.id)[:8]} · {self.get_status_display()}"

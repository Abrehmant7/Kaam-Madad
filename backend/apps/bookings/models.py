"""Bookings made by accepting a quote, arrival codes, change proposals and status history (M8: BK-01..05, QT-04).

- ``Booking``: one accepted quote version of one invitation. ``accepted_terms`` is an immutable snapshot of
  that version (and its agreement-check resolutions); ``terms`` are the terms in effect, which change only
  when both people approve a ``BookingChange``. ``start_at``/``end_at`` reserve the worker.
  Database guarantees (PostgreSQL):
  * one non-cancelled booking per job (``booking_one_per_job``);
  * no overlapping reservations for a worker while a booking is open — half-open ``[start, end)``, so
    back-to-back slots are allowed (``booking_no_worker_overlap``, an exclusion constraint on btree_gist);
  * at most one job in progress per worker (``booking_one_started_per_worker``);
  * an acceptance key is used once per customer (``booking_idempotency_once``).
- ``ArrivalCode``: a six-digit code the customer issues after the worker reports arrival. Only a keyed digest
  is stored; it expires, allows a limited number of wrong attempts and is single-use. Reissue invalidates
  the previous code.
- ``BookingChange``: proposed new scope, price or timing. The current terms stay in effect until the other
  person approves.
- ``BookingEvent``: the status history handed to M9 (never contains a code).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import F, Func, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.conversations.models import Quote
from apps.invitations.models import Invitation
from apps.jobs.models import JobRequest
from apps.workers.models import WorkerProfile


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class Booking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", _("Confirmed")
        ARRIVED = "arrived", _("Worker arrived")
        IN_PROGRESS = "in_progress", _("In progress")
        CANCELLED = "cancelled", _("Cancelled")

    # Statuses that hold the worker's time. M9 adds completion and dispute states to this list.
    RESERVING = (Status.CONFIRMED, Status.ARRIVED, Status.IN_PROGRESS)
    CANCELLABLE = (Status.CONFIRMED, Status.ARRIVED)

    class CancelReason(models.TextChoices):
        NOT_AVAILABLE = "not_available", _("Can no longer make it")
        CHANGED_PLANS = "changed_plans", _("Plans changed")
        NO_SHOW = "no_show", _("The other person did not come or respond")
        OTHER = "other", _("Other")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(JobRequest, on_delete=models.PROTECT, related_name="bookings")
    invitation = models.ForeignKey(Invitation, on_delete=models.PROTECT, related_name="bookings")
    quote = models.ForeignKey(Quote, on_delete=models.PROTECT, related_name="bookings")
    quote_version = models.PositiveIntegerField()
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="customer_bookings")
    worker_profile = models.ForeignKey(WorkerProfile, on_delete=models.PROTECT, related_name="bookings")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CONFIRMED)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    accepted_terms = models.JSONField(help_text=_("Snapshot of the accepted quote version. Never changes."))
    terms = models.JSONField(help_text=_("Terms in effect (the accepted terms plus approved changes)."))
    idempotency_key = models.UUIDField(help_text=_("Sent by the customer's device with the acceptance."))
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    cancelled_role = models.CharField(max_length=16, blank=True, default="")
    cancel_reason = models.CharField(max_length=16, choices=CancelReason.choices, blank=True, default="")
    cancel_note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["worker_profile", "status", "start_at"], name="booking_worker_status_idx")]
        constraints = [
            models.UniqueConstraint(fields=["job"], condition=~Q(status="cancelled"), name="booking_one_per_job"),
            models.UniqueConstraint(fields=["customer", "idempotency_key"], name="booking_idempotency_once"),
            models.UniqueConstraint(fields=["worker_profile"], condition=Q(status="in_progress"),
                                    name="booking_one_started_per_worker"),
            models.CheckConstraint(condition=Q(end_at__gt=F("start_at")), name="booking_end_after_start"),
            models.CheckConstraint(
                condition=(~Q(status="cancelled") | (Q(cancelled_at__isnull=False) & ~Q(cancel_reason="")))
                & (~Q(status="in_progress") | Q(started_at__isnull=False, arrived_at__isnull=False))
                & (~Q(status="arrived") | Q(arrived_at__isnull=False)),
                name="booking_status_has_times",
            ),
            ExclusionConstraint(
                name="booking_no_worker_overlap",
                expressions=[
                    (TsTzRange("start_at", "end_at", RangeBoundary()), RangeOperators.OVERLAPS),  # "[)"
                    ("worker_profile", RangeOperators.EQUAL),
                ],
                condition=Q(status__in=["confirmed", "arrived", "in_progress"]),
            ),
        ]

    def __str__(self) -> str:
        return f"Booking {str(self.id)[:8]} · {self.get_status_display()}"

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_accepted_terms = instance.__dict__.get("accepted_terms")
        return instance

    def save(self, *args, **kwargs):
        loaded = getattr(self, "_loaded_accepted_terms", None)
        if loaded is not None and self.accepted_terms != loaded:
            raise ValueError("The accepted terms of a booking cannot be changed.")
        super().save(*args, **kwargs)
        self._loaded_accepted_terms = self.accepted_terms


class ArrivalCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="arrival_codes")
    digest = models.CharField(max_length=128, help_text=_("Keyed digest. The code itself is never stored."))
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]
        constraints = [
            models.UniqueConstraint(fields=["booking"], condition=Q(used_at__isnull=True, invalidated_at__isnull=True),
                                    name="arrival_code_one_live"),
        ]

    def __str__(self) -> str:
        return f"Arrival code for booking {str(self.booking_id)[:8]}"


class BookingChange(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Waiting for the other person")
        APPROVED = "approved", _("Approved by both")
        REJECTED = "rejected", _("Rejected")
        WITHDRAWN = "withdrawn", _("Withdrawn by the proposer")
        VOID = "void", _("Closed because the booking ended")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="changes")
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    proposed_role = models.CharField(max_length=16)
    note = models.TextField(blank=True, default="")
    old_terms = models.JSONField()
    new_terms = models.JSONField()
    customer_approved_at = models.DateTimeField(null=True, blank=True)
    worker_approved_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_role = models.CharField(max_length=16, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["booking", "number"], name="change_number_once"),
            models.UniqueConstraint(fields=["booking"], condition=Q(status="pending"), name="change_one_pending"),
            models.CheckConstraint(
                condition=~Q(status="approved") | Q(customer_approved_at__isnull=False, worker_approved_at__isnull=False),
                name="change_approved_by_both",
            ),
        ]

    def __str__(self) -> str:
        return f"Change {self.number} · {self.get_status_display()}"


class BookingEvent(models.Model):
    class Kind(models.TextChoices):
        CONFIRMED = "confirmed", _("Quote accepted; booking confirmed")
        ARRIVED = "arrived", _("Worker reported arrival")
        CODE_ISSUED = "code_issued", _("Customer issued an arrival code")
        STARTED = "started", _("Arrival code accepted; work in progress")
        CANCELLED = "cancelled", _("Booking cancelled")
        CHANGE_PROPOSED = "change_proposed", _("Change proposed")
        CHANGE_APPROVED = "change_approved", _("Change approved by both")
        CHANGE_REJECTED = "change_rejected", _("Change rejected")
        CHANGE_WITHDRAWN = "change_withdrawn", _("Change withdrawn")

    id = models.BigAutoField(primary_key=True)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    from_status = models.CharField(max_length=16, blank=True, default="")
    to_status = models.CharField(max_length=16, blank=True, default="")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    actor_role = models.CharField(max_length=16, blank=True, default="")
    note = models.TextField(blank=True, default="")
    data = models.JSONField(default=dict, blank=True)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["at", "id"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} ({str(self.booking_id)[:8]})"

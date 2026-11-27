"""Booking rules (M8). Every write goes through this module.

Lock order, shared with M6/M7 so no two transactions can wait on each other in a cycle:

    JobRequest → Invitation → Quote → WorkerProfile → User → Booking → ArrivalCode / BookingChange

A function locks only the rows it needs, but always in this order, and re-reads them after locking.
Provider calls never happen here (no network inside these transactions).
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework.exceptions import ErrorDetail, NotFound, ValidationError

from apps.conversations import quotes as rules
from apps.conversations.models import Quote
from apps.invitations.models import Invitation
from apps.jobs.models import JobRequest
from apps.workers.models import WorkerProfile

from . import errors
from .models import ArrivalCode, Booking, BookingChange, BookingEvent

logger = logging.getLogger(__name__)
User = get_user_model()

TERM_FIELDS = ("inspection_only", "scope", "quantity", "labour_amount", "labour_basis", "materials", "materials_amount",
               "visit_fee", "visit_fee_treatment", "exclusions", "start_at", "end_at")
MONEY_FIELDS = ("labour_amount", "materials_amount", "visit_fee")
TIME_FIELDS = ("start_at", "end_at")


# --- Roles ------------------------------------------------------------------------------------------------------


def role_in(booking: Booking, user) -> str | None:
    if booking.customer_id == user.pk:
        return "customer"
    if booking.worker_profile.user_id == user.pk:
        return "worker"
    return None


def participant_booking(user, booking_id) -> tuple[Booking, str]:
    """The booking and the caller's role. Anyone else gets 404 (the booking's existence is not revealed)."""
    booking = (Booking.objects.select_related("job", "invitation", "worker_profile__user", "worker_profile__trade")
               .filter(pk=booking_id).first())
    role = role_in(booking, user) if booking else None
    if role is None:
        raise NotFound()
    return booking, role


def _lock_booking_rows(booking: Booking, *, invitation=False, worker=False) -> Booking:
    """Lock the rows of an existing booking in the shared order and return the re-read booking."""
    JobRequest.objects.select_for_update().get(pk=booking.job_id)
    if invitation:
        Invitation.objects.select_for_update().get(pk=booking.invitation_id)
    if worker:
        WorkerProfile.objects.select_for_update().get(pk=booking.worker_profile_id)
    return Booking.objects.select_for_update().select_related("job", "invitation", "worker_profile__user").get(pk=booking.pk)


def _event(booking, kind, user, role, *, from_status="", note="", data=None):
    BookingEvent.objects.create(booking=booking, kind=kind, from_status=from_status, to_status=booking.status,
                                actor=user, actor_role=role, note=note, data=data or {})


# --- Terms ------------------------------------------------------------------------------------------------------


def _serialize(name, value):
    if value is None:
        return None
    if name in MONEY_FIELDS:
        return rules._money(value)
    if name in TIME_FIELDS:
        return rules.iso_utc(value)
    return value


def terms_of(obj) -> dict:
    """The structured terms of a quote (or an unsaved quote built from a change), in API form."""
    terms = {name: _serialize(name, getattr(obj, name)) for name in TERM_FIELDS}
    terms["materials"] = terms["materials"] or None
    return terms


def accepted_snapshot(quote: Quote, now) -> dict:
    resolutions = [
        {"code": f.code, "source": f.source, "resolution": f.resolution or None, "note": f.resolution_note or None,
         "resolved_role": f.resolved_role or None, "resolved_at": rules.iso_utc(f.resolved_at), "status": f.status}
        for f in quote.findings.all()
    ]
    return {
        **terms_of(quote),
        "totals": quote.totals,
        "quote_id": str(quote.id),
        "version": quote.version,
        "submitted_at": rules.iso_utc(quote.submitted_at),
        "accepted_at": rules.iso_utc(now),
        "check": {"status": rules.effective_check_status(quote, now), "provider": quote.check_provider or None,
                  "simulated": quote.check_simulated, "manual_review_at": rules.iso_utc(quote.manual_review_at)},
        "resolutions": resolutions,
    }


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _overlaps(worker_profile_id, start, end, *, exclude=None) -> bool:
    queryset = Booking.objects.filter(worker_profile_id=worker_profile_id, status__in=Booking.RESERVING,
                                      start_at__lt=end, end_at__gt=start)  # half-open [start, end)
    if exclude is not None:
        queryset = queryset.exclude(pk=exclude)
    return queryset.exists()


# --- Acceptance (BK-01, BK-03) ----------------------------------------------------------------------------------


def accept_quote(user, *, invitation_id, quote_id, version, key) -> tuple[Booking, bool]:
    """Create the booking for exactly this quote version. Returns (booking, created)."""
    first = Invitation.objects.select_related("job").filter(pk=invitation_id).first()
    if first is None or first.job.customer_id != user.pk:
        raise NotFound()
    now = timezone.now()
    with transaction.atomic():
        job = JobRequest.objects.select_for_update().get(pk=first.job_id)                       # 1. job
        same_key = Booking.objects.filter(customer=user, idempotency_key=key).first()
        if same_key is not None:
            if str(same_key.invitation_id) == str(invitation_id) and str(same_key.quote_id) == str(quote_id):
                return same_key, False  # a retry: the original booking, whatever happened to it since
            raise errors.IdempotencyKeyReused(details={"booking_id": str(same_key.id)})
        invitation = Invitation.objects.select_for_update().get(pk=invitation_id)               # 2. invitation
        booked = Booking.objects.filter(job=job).exclude(status=Booking.Status.CANCELLED).first()
        if booked is not None:
            raise errors.JobAlreadyBooked(details={"booking_id": str(booked.id)})
        if invitation.status != Invitation.Status.ACTIVE:
            raise errors.InvitationNotActive(details={"invitation_status": invitation.status})
        quote = Quote.objects.select_for_update().filter(pk=quote_id, invitation=invitation).first()  # 3. quote
        current = invitation.quotes.filter(status=Quote.Status.SUBMITTED).first()
        if quote is None or quote.status != Quote.Status.SUBMITTED or quote.version != version:
            raise errors.QuoteNotCurrent(details={"current_quote_id": str(current.id) if current else None,
                                                  "current_version": current.version if current else None})
        worker = WorkerProfile.objects.select_for_update().get(pk=invitation.worker_profile_id)  # 4. worker
        worker.user = User.objects.select_for_update().get(pk=worker.user_id)                  #    and account
        invitation.worker_profile = worker
        state = rules.readiness(invitation, quote, now)
        if not state["ready"]:
            if "quote_expired" in state["blocking"]:
                raise errors.QuoteExpired(details={"expires_at": state["expires_at"]})
            if "worker_not_eligible" in state["blocking"]:
                raise errors.WorkerNotEligible()
            raise errors.QuoteNotReady(details={"blocking": state["blocking"]})
        if _overlaps(worker.pk, quote.start_at, quote.end_at):
            raise errors.ScheduleConflict()
        snapshot = accepted_snapshot(quote, now)
        effective = {**terms_of(quote), "totals": quote.totals, "source": {"kind": "quote", "version": quote.version}}
        try:
            with transaction.atomic():
                booking = Booking.objects.create(
                    job=job, invitation=invitation, quote=quote, quote_version=quote.version, customer=user,
                    worker_profile=worker, start_at=quote.start_at, end_at=quote.end_at, accepted_terms=snapshot,
                    terms=effective, idempotency_key=key, created_at=now,
                )
        except IntegrityError:  # backstop for the database guarantees (same key, same job, overlapping time)
            if Booking.objects.filter(customer=user, idempotency_key=key).exists():
                raise errors.IdempotencyKeyReused() from None
            if Booking.objects.filter(job=job).exclude(status=Booking.Status.CANCELLED).exists():
                raise errors.JobAlreadyBooked() from None
            raise errors.ScheduleConflict() from None
        _event(booking, BookingEvent.Kind.CONFIRMED, user, "customer", data={"quote_version": quote.version})
    logger.info("Quote accepted; booking confirmed.")
    return booking, True


# --- Arrival and start (BK-04) ----------------------------------------------------------------------------------


def mark_arrived(user, booking_id) -> Booking:
    booking, role = participant_booking(user, booking_id)
    if role != "worker":
        raise errors.NotYourAction()
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status == Booking.Status.ARRIVED:
            return booking  # a retry
        if booking.status != Booking.Status.CONFIRMED:
            raise errors.BookingStateConflict(details={"status": booking.status})
        booking.status, booking.arrived_at = Booking.Status.ARRIVED, timezone.now()
        booking.save(update_fields=["status", "arrived_at", "updated_at"])
        _event(booking, BookingEvent.Kind.ARRIVED, user, role, from_status=Booking.Status.CONFIRMED)
    return booking


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def code_digest(booking_id, code: str) -> str:
    """Keyed digest (HMAC-SHA256 with a key derived from SECRET_KEY), bound to the booking."""
    return salted_hmac("kaam-madad.arrival-code", f"{booking_id}:{code}", algorithm="sha256").hexdigest()


def _live_codes(booking):
    return booking.arrival_codes.filter(used_at__isnull=True, invalidated_at__isnull=True)


def issue_code(user, booking_id) -> tuple[str, ArrivalCode]:
    """The customer reveals a new code. Returns the plaintext ONCE; only its digest is stored."""
    booking, role = participant_booking(user, booking_id)
    if role != "customer":
        raise errors.NotYourAction()
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        if booking.status != Booking.Status.ARRIVED:
            raise errors.BookingStateConflict(details={"status": booking.status})
        now = timezone.now()
        _live_codes(booking).select_for_update().update(invalidated_at=now)  # reissue invalidates the old code
        code = generate_code()
        row = ArrivalCode.objects.create(booking=booking, digest=code_digest(booking.pk, code), issued_by=user,
                                         issued_at=now, expires_at=now + timedelta(minutes=settings.ARRIVAL_CODE_TTL_MINUTES))
        _event(booking, BookingEvent.Kind.CODE_ISSUED, user, role, from_status=booking.status)
    logger.info("Arrival code issued.")  # never the code
    return code, row


def start_with_code(user, booking_id, code: str) -> Booking:
    """The assigned worker enters the customer's code. Wrong attempts are counted even though the call fails."""
    booking, role = participant_booking(user, booking_id)
    if role != "worker":
        raise errors.NotYourAction()
    failure = None
    with transaction.atomic():
        booking = _lock_booking_rows(booking, worker=True)  # job → worker → booking: serialises starts per worker
        if booking.status == Booking.Status.IN_PROGRESS:
            return booking  # a retry after the code was accepted
        if booking.status != Booking.Status.ARRIVED:
            raise errors.BookingStateConflict(details={"status": booking.status})
        if Booking.objects.filter(worker_profile_id=booking.worker_profile_id, status=Booking.Status.IN_PROGRESS).exists():
            raise errors.WorkerBusy()
        live = _live_codes(booking).select_for_update().first()
        if live is None:
            raise errors.NoActiveCode()
        limit = settings.ARRIVAL_CODE_MAX_ATTEMPTS
        if live.failed_attempts >= limit:
            raise errors.TooManyAttempts()
        now = timezone.now()
        if now >= live.expires_at:
            raise errors.CodeExpired()
        if not constant_time_compare(live.digest, code_digest(booking.pk, code)):
            live.failed_attempts += 1
            live.save(update_fields=["failed_attempts"])  # committed: the failure is raised after the block
            remaining = limit - live.failed_attempts
            failure = errors.TooManyAttempts() if remaining <= 0 else errors.CodeIncorrect(details={"attempts_remaining": remaining})
        else:
            live.used_at = now
            live.save(update_fields=["used_at"])
            booking.status, booking.started_at = Booking.Status.IN_PROGRESS, now
            try:
                with transaction.atomic():
                    booking.save(update_fields=["status", "started_at", "updated_at"])
            except IntegrityError:  # backstop: one job in progress per worker
                raise errors.WorkerBusy() from None
            _event(booking, BookingEvent.Kind.STARTED, user, role, from_status=Booking.Status.ARRIVED)
    if failure is not None:
        logger.info("Arrival code rejected.")
        raise failure
    logger.info("Arrival code accepted; work in progress.")
    return booking


# --- Cancellation (BK-06, before start) -------------------------------------------------------------------------


def cancel(user, booking_id, *, reason: str, note: str) -> Booking:
    booking, role = participant_booking(user, booking_id)
    with transaction.atomic():
        booking = _lock_booking_rows(booking, invitation=True, worker=True)
        if booking.status == Booking.Status.CANCELLED:
            return booking
        if booking.status not in Booking.CANCELLABLE:
            raise errors.CancelNotAllowed(details={"status": booking.status})
        now = timezone.now()
        previous = booking.status
        booking.status, booking.cancelled_at, booking.cancelled_by = Booking.Status.CANCELLED, now, user
        booking.cancelled_role, booking.cancel_reason, booking.cancel_note = role, reason, note
        booking.save(update_fields=["status", "cancelled_at", "cancelled_by", "cancelled_role", "cancel_reason",
                                    "cancel_note", "updated_at"])
        invitation = booking.invitation
        if invitation.status == Invitation.Status.ACTIVE:  # its quote can never be accepted again
            invitation.status, invitation.closed_at = Invitation.Status.CANCELLED, now
            invitation.save(update_fields=["status", "closed_at"])
        _live_codes(booking).update(invalidated_at=now)
        booking.changes.filter(status=BookingChange.Status.PENDING).update(status=BookingChange.Status.VOID, decided_at=now)
        _event(booking, BookingEvent.Kind.CANCELLED, user, role, from_status=previous, note=note, data={"reason": reason})
    logger.info("Booking cancelled before start.")
    return booking


# --- Changes after booking (QT-04) ------------------------------------------------------------------------------


def _check_new_terms(values: dict, time_changed: bool, now) -> dict:
    """Validate proposed terms with the quote rules. Unchanged past times are not an error during the job."""
    draft = Quote(**{name: values.get(name) for name in TERM_FIELDS})
    draft.materials = draft.materials or ""
    problems = rules.validate(draft, now)
    if not time_changed:
        for name in TIME_FIELDS:
            kept = [(c, m) for c, m in problems.get(name, []) if c not in ("window_in_past", "window_too_far")]
            if kept:
                problems[name] = kept
            else:
                problems.pop(name, None)
    if problems:
        raise ValidationError({name: [ErrorDetail(m, code=c) for c, m in items] for name, items in problems.items()})
    return {**terms_of(draft), "totals": rules.compute_totals(draft)}


def propose_change(user, booking_id, values: dict, note: str) -> BookingChange:
    booking, role = participant_booking(user, booking_id)
    with transaction.atomic():
        booking = _lock_booking_rows(booking, worker=True)
        if booking.status not in Booking.RESERVING:
            raise errors.BookingStateConflict(details={"status": booking.status})
        if booking.changes.filter(status=BookingChange.Status.PENDING).exists():
            raise errors.ChangePending()
        now = timezone.now()
        current = {name: booking.terms.get(name) for name in TERM_FIELDS}
        proposed_plain = terms_of(Quote(**{name: values.get(name) for name in TERM_FIELDS}))
        changed = [name for name in TERM_FIELDS if proposed_plain[name] != current[name]]
        if not changed:
            raise ValidationError({"non_field_errors": [ErrorDetail("Nothing was changed.", code="no_change")]})
        time_changed = any(name in TIME_FIELDS for name in changed)
        if time_changed and booking.status != Booking.Status.CONFIRMED:
            raise errors.TimeChangeNotAllowed(details={"status": booking.status})
        proposed = _check_new_terms(values, time_changed, now)
        if time_changed and _overlaps(booking.worker_profile_id, values["start_at"], values["end_at"], exclude=booking.pk):
            raise errors.ScheduleConflict()
        number = (booking.changes.order_by("-number").values_list("number", flat=True).first() or 0) + 1
        change = BookingChange.objects.create(
            booking=booking, number=number, proposed_by=user, proposed_role=role, note=note,
            old_terms={**current, "totals": booking.terms.get("totals")}, new_terms=proposed,
            customer_approved_at=now if role == "customer" else None, worker_approved_at=now if role == "worker" else None,
        )
        _event(booking, BookingEvent.Kind.CHANGE_PROPOSED, user, role, from_status=booking.status, note=note,
               data={"number": number, "fields": changed})
    return change


def decide_change(user, booking_id, change_id, action: str) -> BookingChange:
    """approve / reject (the other person) or withdraw (the proposer)."""
    booking, role = participant_booking(user, booking_id)
    with transaction.atomic():
        booking = _lock_booking_rows(booking, worker=True)
        change = booking.changes.select_for_update().filter(pk=change_id).first()
        if change is None:
            raise NotFound()
        if change.status != BookingChange.Status.PENDING:
            raise errors.ChangeNotPending(details={"status": change.status})
        mine = change.proposed_role == role
        if (action == "withdraw") != mine:
            raise errors.NotYourAction()
        now = timezone.now()
        if action in ("reject", "withdraw"):
            change.status = BookingChange.Status.REJECTED if action == "reject" else BookingChange.Status.WITHDRAWN
            kind = BookingEvent.Kind.CHANGE_REJECTED if action == "reject" else BookingEvent.Kind.CHANGE_WITHDRAWN
        else:
            if booking.status not in Booking.RESERVING:
                raise errors.BookingStateConflict(details={"status": booking.status})
            new = change.new_terms
            start, end = _parse_time(new["start_at"]), _parse_time(new["end_at"])
            time_changed = (new["start_at"], new["end_at"]) != (booking.terms.get("start_at"), booking.terms.get("end_at"))
            if time_changed:
                if booking.status != Booking.Status.CONFIRMED:
                    raise errors.TimeChangeNotAllowed(details={"status": booking.status})
                if start <= now:
                    raise ValidationError({"start_at": [ErrorDetail("The proposed time has passed.", code="window_in_past")]})
                if _overlaps(booking.worker_profile_id, start, end, exclude=booking.pk):  # re-checked under the worker lock
                    raise errors.ScheduleConflict()
            setattr(change, f"{role}_approved_at", now)
            booking.terms = {**new, "source": {"kind": "change", "number": change.number}}
            booking.start_at, booking.end_at = start, end
            try:
                with transaction.atomic():
                    booking.save(update_fields=["terms", "start_at", "end_at", "updated_at"])
            except IntegrityError:  # backstop: the exclusion constraint
                raise errors.ScheduleConflict() from None
            change.status = BookingChange.Status.APPROVED
            kind = BookingEvent.Kind.CHANGE_APPROVED
        change.decided_at, change.decided_by, change.decided_role = now, user, role
        change.save()
        _event(booking, kind, user, role, from_status=booking.status, data={"number": change.number})
    return change


# --- Guards used by M6/M7 ---------------------------------------------------------------------------------------


def booking_for_invitation(invitation_id) -> Booking | None:
    return Booking.objects.filter(invitation_id=invitation_id).exclude(status=Booking.Status.CANCELLED).first()


def booking_for_job(job_id) -> Booking | None:
    return Booking.objects.filter(job_id=job_id).exclude(status=Booking.Status.CANCELLED).first()

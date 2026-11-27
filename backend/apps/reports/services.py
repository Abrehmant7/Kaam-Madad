"""Reports, moderation, restrictions and blocks (M10). Never logs report text, file names or transcripts."""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ErrorDetail, NotFound, PermissionDenied, ValidationError

from apps.bookings.models import Booking
from apps.core.api.exceptions import ApiError
from apps.invitations.models import Invitation
from apps.jobs.photos import clean_photo
from apps.voice.models import AudioClip, Purpose

from .models import ContactBlock, EvidenceAccess, Report, ReportDecision, ReportEvidence, ReportMessage

logger = logging.getLogger(__name__)
User = get_user_model()
MAX_EVIDENCE = 5


class AccountRestricted(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "account_restricted"
    default_detail = "Your account is restricted. You can view your records, file reports and reply to staff."


class ContactBlocked(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "contact_blocked"
    default_detail = "Further contact between these accounts is blocked."


class ReportClosed(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "report_closed"
    default_detail = "This report is closed."


class TooMuchEvidence(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "too_much_evidence"
    default_detail = f"At most {MAX_EVIDENCE} evidence items per report."


# --- Guards used by M5–M8 -------------------------------------------------------------------------------------


def require_unrestricted(user) -> None:
    if getattr(user, "restricted_at", None) is not None:
        raise AccountRestricted()


def is_blocked(user_a, user_b) -> bool:
    """True if either user blocked the other (blocks work in both directions)."""
    a, b = getattr(user_a, "pk", user_a), getattr(user_b, "pk", user_b)
    return ContactBlock.objects.filter(Q(blocker_id=a, blocked_id=b) | Q(blocker_id=b, blocked_id=a)).exists()


def require_not_blocked(user_a, user_b) -> None:
    if is_blocked(user_a, user_b):
        raise ContactBlocked()


def blocked_user_ids(user) -> set:
    rows = ContactBlock.objects.filter(Q(blocker=user) | Q(blocked=user)).values_list("blocker_id", "blocked_id")
    return {other for pair in rows for other in pair if other != user.pk}


# --- Interactions -----------------------------------------------------------------------------------------------


def interaction_for(user, *, invitation_id=None, booking_id=None) -> tuple[Invitation, Booking | None, str, object]:
    """(invitation, booking, my role, the OTHER participant) — 404 unless the caller took part."""
    booking = None
    if booking_id:
        booking = Booking.objects.select_related("invitation__job", "invitation__worker_profile__user").filter(pk=booking_id).first()
        invitation = booking.invitation if booking else None
    else:
        invitation = Invitation.objects.select_related("job", "worker_profile__user").filter(pk=invitation_id).first()
    if invitation is None:
        raise NotFound()
    customer, worker = invitation.job.customer, invitation.worker_profile.user
    if user.pk == customer.pk:
        return invitation, booking, "customer", worker
    if user.pk == worker.pk:
        return invitation, booking, "worker", customer
    raise NotFound()  # never reveal another pair's interaction


# --- Filing -----------------------------------------------------------------------------------------------------


def file_report(user, *, client_id, category, description="", invitation_id=None, booking_id=None, audio_clip_id=None) -> tuple[Report, bool]:
    """Allowed for restricted users and after the interaction closed. Changes nothing about the booking."""
    invitation, booking, role, other = interaction_for(user, invitation_id=invitation_id, booking_id=booking_id)
    with transaction.atomic():
        existing = Report.objects.filter(reporter=user, client_id=client_id).first()
        if existing is not None:
            return existing, False  # a retry
        clip = None
        if audio_clip_id:
            clip = AudioClip.objects.filter(pk=audio_clip_id, owner=user, purpose=Purpose.REPORT).first()
            if clip is None or ReportEvidence.objects.filter(audio_clip=clip).exists():
                raise ValidationError({"audio_clip_id": [ErrorDetail("Recording not found.", code="not_found")]})
        if not description.strip() and clip is None:
            raise ValidationError({"description": [ErrorDetail("Describe what happened or record a voice note.", code="required")]})
        try:
            with transaction.atomic():
                report = Report.objects.create(reporter=user, reporter_role=role, reported=other, invitation=invitation,
                                               booking=booking, client_id=client_id, category=category,
                                               description=description.strip())
        except IntegrityError:
            return Report.objects.get(reporter=user, client_id=client_id), False
        if clip is not None:
            ReportEvidence.objects.create(report=report, kind=ReportEvidence.Kind.AUDIO, role=ReportEvidence.Role.STATEMENT,
                                          audio_clip=clip, mime_type=clip.mime_type, size_bytes=clip.size_bytes)
    logger.info("Report filed (category=%s).", category)
    return report, True


def own_report(user, report_id) -> Report:
    report = Report.objects.filter(pk=report_id, reporter=user).first()
    if report is None:
        raise NotFound()  # the reported user and everyone else get 404
    return report


def add_evidence(user, report_id, *, image: bytes | None = None, audio_clip_id=None) -> ReportEvidence:
    with transaction.atomic():
        report = Report.objects.select_for_update().filter(pk=report_id, reporter=user).first()
        if report is None:
            raise NotFound()
        if report.status in Report.CLOSED:
            raise ReportClosed()
        if report.evidence.filter(role=ReportEvidence.Role.EVIDENCE).count() >= MAX_EVIDENCE:
            raise TooMuchEvidence()
        if image is not None:
            clean = clean_photo(image)  # content checks + re-encode without metadata (EXIF/GPS removed)
            item = ReportEvidence(report=report, kind=ReportEvidence.Kind.IMAGE, mime_type=clean.mime_type, size_bytes=len(clean.data))
            item.file.save("evidence", ContentFile(clean.data), save=False)
            item.save()
        else:
            clip = AudioClip.objects.filter(pk=audio_clip_id, owner=user, purpose=Purpose.REPORT).first()
            if clip is None or ReportEvidence.objects.filter(audio_clip=clip).exists():
                raise ValidationError({"audio_clip_id": [ErrorDetail("Recording not found.", code="not_found")]})
            item = ReportEvidence.objects.create(report=report, kind=ReportEvidence.Kind.AUDIO, audio_clip=clip,
                                                 mime_type=clip.mime_type, size_bytes=clip.size_bytes)
    logger.info("Report evidence added (kind=%s).", item.kind)
    return item


def add_reply(user, report_id, text: str) -> ReportMessage:
    with transaction.atomic():
        report = Report.objects.select_for_update().filter(pk=report_id, reporter=user).first()
        if report is None:
            raise NotFound()
        if report.status in Report.CLOSED:
            raise ReportClosed()
        message = ReportMessage.objects.create(report=report, kind=ReportMessage.Kind.REPORTER_REPLY, author=user, text=text)
        if report.awaiting_reply:
            report.awaiting_reply = False
            report.save(update_fields=["awaiting_reply", "updated_at"])
    return message


# --- Staff ------------------------------------------------------------------------------------------------------


def _require_perm(staff, perm: str) -> None:
    if not (staff.is_active and staff.is_staff and staff.has_perm(perm)):
        raise PermissionDenied()


def _account_state(user) -> dict:
    return {"is_active": user.is_active, "restricted": user.restricted_at is not None}


def decide(staff, report_id, *, action: str, reason: str, message_to_reporter: str = "", internal_note: str = "",
           account_action: str = "", account_reason: str = "") -> Report:
    """Record one staff decision (and optionally one account action on the REPORTED user), fully audited."""
    _require_perm(staff, "reports.review_report")
    reason, message_to_reporter = reason.strip(), message_to_reporter.strip()
    if len(reason) < 3:
        raise ValidationError({"reason": [ErrorDetail("Give the reason for this decision.", code="required")]})
    if action in (ReportDecision.Action.REQUEST_INFO, ReportDecision.Action.RESOLVE, ReportDecision.Action.DISMISS) and not message_to_reporter:
        raise ValidationError({"message_to_reporter": [ErrorDetail("Write what the reporter should see.", code="required")]})
    if account_action:
        _require_perm(staff, "reports.take_account_action")
        if len(account_reason.strip()) < 3:
            raise ValidationError({"account_reason": [ErrorDetail("Give the reason for the account action.", code="required")]})
    now = timezone.now()
    with transaction.atomic():
        report = Report.objects.select_for_update().filter(pk=report_id).first()
        if report is None:
            raise NotFound()
        old = {"status": report.status, "awaiting_reply": report.awaiting_reply}
        if action == ReportDecision.Action.MARK_REVIEWING:
            if report.status in Report.CLOSED:
                raise ReportClosed()
            report.status = Report.Status.REVIEWING
        elif action == ReportDecision.Action.REQUEST_INFO:
            if report.status in Report.CLOSED:
                raise ReportClosed()
            report.status, report.awaiting_reply = Report.Status.REVIEWING, True
        elif action in (ReportDecision.Action.RESOLVE, ReportDecision.Action.DISMISS):
            if report.status in Report.CLOSED:
                raise ReportClosed()
            report.status = Report.Status.RESOLVED if action == ReportDecision.Action.RESOLVE else Report.Status.DISMISSED
            report.awaiting_reply, report.closed_at = False, now
        elif action != ReportDecision.Action.NOTE:
            raise ValidationError({"action": [ErrorDetail("Choose an action.", code="invalid_choice")]})
        report.save(update_fields=["status", "awaiting_reply", "closed_at", "updated_at"])
        ReportDecision.objects.create(report=report, action=action, actor=staff, reason=reason, old_state=old,
                                      new_state={"status": report.status, "awaiting_reply": report.awaiting_reply}, at=now)
        if message_to_reporter:
            ReportMessage.objects.create(report=report, kind=ReportMessage.Kind.TO_REPORTER, author=staff, text=message_to_reporter)
        if internal_note.strip():
            ReportMessage.objects.create(report=report, kind=ReportMessage.Kind.INTERNAL, author=staff, text=internal_note.strip())
        if account_action:
            apply_account_action(staff, report, account_action, account_reason.strip(), now)
    logger.info("Report decision recorded (action=%s, account_action=%s).", action, account_action or "none")
    return report


def apply_account_action(staff, report: Report, account_action: str, reason: str, now) -> None:
    """Restrict / lift / suspend / reactivate the REPORTED user only. The report and evidence stay unchanged."""
    target = User.objects.select_for_update().get(pk=report.reported_id)
    old = _account_state(target)
    if account_action == ReportDecision.Action.RESTRICT:
        target.restricted_at = target.restricted_at or now
    elif account_action == ReportDecision.Action.LIFT_RESTRICTION:
        target.restricted_at = None
    elif account_action == ReportDecision.Action.SUSPEND:
        target.is_active = False  # existing behaviour: no login, sessions no longer authenticate
    elif account_action == ReportDecision.Action.REACTIVATE:
        target.is_active = True
    else:
        raise ValidationError({"account_action": [ErrorDetail("Choose an account action.", code="invalid_choice")]})
    target.save(update_fields=["restricted_at", "is_active", "updated_at"])
    ReportDecision.objects.create(report=report, action=account_action, actor=staff, reason=reason, old_state=old,
                                  new_state=_account_state(target), at=now)


def open_evidence_for_staff(staff, evidence_id) -> ReportEvidence:
    """Permission-checked and recorded BEFORE the content is returned."""
    _require_perm(staff, "reports.view_evidence")
    evidence = ReportEvidence.objects.select_related("audio_clip").filter(pk=evidence_id, deleted_at__isnull=True).first()
    if evidence is None:
        raise NotFound()
    EvidenceAccess.objects.create(evidence=evidence, staff=staff)
    return evidence


# --- Blocks -----------------------------------------------------------------------------------------------------


def block(user, *, invitation_id=None, booking_id=None) -> ContactBlock:
    """Allowed for restricted users too. History, reports and existing bookings are untouched."""
    invitation, _booking, _role, other = interaction_for(user, invitation_id=invitation_id, booking_id=booking_id)
    try:
        with transaction.atomic():
            return ContactBlock.objects.create(blocker=user, blocked=other, invitation=invitation)
    except IntegrityError:
        return ContactBlock.objects.get(blocker=user, blocked=other)


def unblock(user, block_id) -> None:
    deleted, _ = ContactBlock.objects.filter(pk=block_id, blocker=user).delete()
    if not deleted:
        raise NotFound()


def block_state(user, other) -> dict:
    mine = ContactBlock.objects.filter(blocker=user, blocked=other).first()
    theirs = ContactBlock.objects.filter(blocker=other, blocked=user).exists()
    # The other person's block is not attributed: only "contact is blocked".
    return {"blocked": bool(mine) or theirs, "by_me": bool(mine), "block_id": str(mine.id) if mine else None}

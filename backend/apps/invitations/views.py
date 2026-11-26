"""Recommendations and targeted invitations (M6). Contracts: docs/api.md § Recommendations and invitations.

Customer endpoints live under /jobs/{id}/ and are scoped to the request owner (others: 404,
workers: 403). Worker endpoints live under /invitations/ and only ever return invitations
addressed to the signed-in worker (others: 404). Workers see only the shared summary.
"""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.exceptions import ErrorDetail, NotFound, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsCustomer, IsWorker
from apps.accounts.serializers import StrictFieldsMixin
from apps.accounts.throttles import ConfigurableRateThrottle
from apps.core.api.exceptions import ApiError
from apps.jobs import rules as job_rules
from apps.jobs.models import JobRequest
from apps.jobs.summary import matching_summary, privacy_warnings
from apps.jobs.views import job_payload, own_jobs

from . import matching
from .models import Invitation

logger = logging.getLogger(__name__)


class InvitationThrottle(ConfigurableRateThrottle):
    scope = "invitation_user"

    def get_cache_key(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS") or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class NotConfirmed(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "request_not_confirmed"
    default_detail = "Confirm the request before finding workers."


class InvitationActive(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "invitation_already_active"
    default_detail = "This request already has an active invitation. Withdraw it before inviting someone else."


class InvitationClosed(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "invitation_closed"
    default_detail = "This invitation is already closed."


# --- Payloads ---------------------------------------------------------------------------------------


def shared_view(summary: dict) -> dict:
    """What a worker may see: the matching summary without internal identifiers."""
    return {key: value for key, value in summary.items() if key != "id"}


def customer_invitation_payload(invitation: Invitation) -> dict:
    profile = invitation.worker_profile
    return {
        "id": str(invitation.id),
        "status": invitation.status,
        "worker": {"worker_id": str(profile.id), "display_label": None, "trade": profile.trade.code if profile.trade else None},
        "created_at": invitation.created_at.isoformat(),
        "seen_at": invitation.seen_at.isoformat() if invitation.seen_at else None,
        "closed_at": invitation.closed_at.isoformat() if invitation.closed_at else None,
        "decline_reason": invitation.decline_reason or None,
    }


def worker_invitation_payload(invitation: Invitation) -> dict:
    return {
        "id": str(invitation.id),
        "status": invitation.status,
        "created_at": invitation.created_at.isoformat(),
        "seen_at": invitation.seen_at.isoformat() if invitation.seen_at else None,
        "closed_at": invitation.closed_at.isoformat() if invitation.closed_at else None,
        "decline_reason": invitation.decline_reason or None,
        # Only the shareable summary: no address, access notes, photos, recordings or customer identity.
        "job": shared_view(invitation.shared_summary),
    }


def _confirmed_job(request, job_id) -> JobRequest:
    job = own_jobs(request).filter(pk=job_id).first()
    if job is None:
        raise NotFound()
    if job.status != JobRequest.Status.CONFIRMED:
        raise NotConfirmed()
    return job


def _active(job: JobRequest) -> Invitation | None:
    return job.invitations.filter(status=Invitation.Status.ACTIVE).select_related("worker_profile__trade").first()


# --- Customer --------------------------------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class RecommendationsView(APIView):
    """GET /jobs/{id}/recommendations/ — matching workers, the shared preview and the current invitation."""

    permission_classes = [IsCustomer]

    def get(self, request, job_id):
        job = _confirmed_job(request, job_id)
        summary = matching_summary(job)
        history = {}
        for invitation in job.invitations.order_by("created_at"):
            history[str(invitation.worker_profile_id)] = invitation.status
        workers = [matching.worker_card(m, history.get(str(m.profile.id))) for m in matching.recommend(summary)]
        active = _active(job)
        return Response({
            "request": {"trade": summary["trade"], "services": summary["services"], "city": summary["city"],
                        "area": summary["area"], "window_start": summary["window_start"], "window_end": summary["window_end"]},
            "shared_preview": shared_view(summary),
            "privacy_warnings": privacy_warnings(summary["description"]),
            "workers": workers,
            "active_invitation": customer_invitation_payload(active) if active else None,
        })


class SendSerializer(StrictFieldsMixin, serializers.Serializer):
    worker_id = serializers.UUIDField()


class DescriptionSerializer(StrictFieldsMixin, serializers.Serializer):
    description = serializers.CharField(max_length=job_rules.MAX_DESCRIPTION, trim_whitespace=True)


def send_invitation(job_id, customer, worker_id) -> tuple[Invitation, bool]:
    """Create the active invitation (or return the same one). Raises API errors on conflicts."""
    with transaction.atomic():
        # Row lock on the request serialises concurrent sends for the same request.
        job = JobRequest.objects.select_for_update().filter(pk=job_id, customer=customer).first()
        if job is None:
            raise NotFound()
        if job.status != JobRequest.Status.CONFIRMED:
            raise NotConfirmed()
        active = job.invitations.filter(status=Invitation.Status.ACTIVE).first()
        if active is not None:
            if str(active.worker_profile_id) == str(worker_id):
                return active, False  # retry of the same send
            raise InvitationActive(details={"invitation_id": str(active.id)})
        summary = matching_summary(job)
        profile = matching.candidate_profiles(summary).filter(pk=worker_id).first()
        if profile is None or matching.match_profile(profile, summary) is None:
            # Re-checked now: the worker may have paused, been suspended or changed areas since listing.
            raise ValidationError({"worker_id": [ErrorDetail("This worker cannot receive this request now.",
                                                             code="worker_not_available")]})
        try:
            with transaction.atomic():
                invitation = Invitation.objects.create(job=job, worker_profile=profile, shared_summary=summary)
        except IntegrityError:
            # Backstop: the partial unique index (one active per request) rejected a second active row.
            existing = job.invitations.filter(status=Invitation.Status.ACTIVE).first()
            if existing and str(existing.worker_profile_id) == str(worker_id):
                return existing, False
            raise InvitationActive(details={"invitation_id": str(existing.id) if existing else None}) from None
    logger.info("Invitation sent.")
    return invitation, True


@method_decorator(never_cache, name="dispatch")
class JobInvitationsView(APIView):
    """GET /jobs/{id}/invitations/ (history, newest first) · POST {worker_id} → send."""

    permission_classes = [IsCustomer]
    throttle_classes = [InvitationThrottle]

    def get(self, request, job_id):
        job = own_jobs(request).filter(pk=job_id).first()
        if job is None:
            raise NotFound()
        invitations = job.invitations.select_related("worker_profile__trade").order_by("-created_at")
        return Response({"results": [customer_invitation_payload(i) for i in invitations]})

    def post(self, request, job_id):
        serializer = SendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation, created = send_invitation(job_id, request.user, serializer.validated_data["worker_id"])
        invitation = Invitation.objects.select_related("worker_profile__trade").get(pk=invitation.pk)
        return Response({**customer_invitation_payload(invitation), "created": created},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@method_decorator(never_cache, name="dispatch")
class WithdrawView(APIView):
    """POST /jobs/{id}/invitations/{invitation_id}/withdraw/ — the request owner closes it (idempotent)."""

    permission_classes = [IsCustomer]
    throttle_classes = [InvitationThrottle]

    def post(self, request, job_id, invitation_id):
        with transaction.atomic():
            invitation = (
                Invitation.objects.select_for_update()
                .filter(pk=invitation_id, job_id=job_id, job__customer=request.user)
                .first()
            )
            if invitation is None:
                raise NotFound()
            if invitation.status == Invitation.Status.DECLINED:
                raise InvitationClosed()
            if invitation.status == Invitation.Status.ACTIVE:
                invitation.status = Invitation.Status.WITHDRAWN
                invitation.closed_at = timezone.now()
                invitation.save(update_fields=["status", "closed_at"])
        invitation = Invitation.objects.select_related("worker_profile__trade").get(pk=invitation.pk)
        return Response(customer_invitation_payload(invitation))


@method_decorator(never_cache, name="dispatch")
class SharedDescriptionView(APIView):
    """PATCH /jobs/{id}/shared-description/ {description} — before inviting, the customer may edit the
    free-text description of a CONFIRMED request (e.g. to remove a phone number or address). Not while an
    invitation is active, so what a worker already received never changes underneath them."""

    permission_classes = [IsCustomer]
    throttle_classes = [InvitationThrottle]

    def patch(self, request, job_id):
        serializer = DescriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            job = JobRequest.objects.select_for_update().filter(pk=job_id, customer=request.user).first()
            if job is None:
                raise NotFound()
            if job.status != JobRequest.Status.CONFIRMED:
                raise NotConfirmed()
            if job.invitations.filter(status=Invitation.Status.ACTIVE).exists():
                raise InvitationActive()
            job.description = serializer.validated_data["description"]
            job.save(update_fields=["description", "updated_at"])
        payload = job_payload(own_jobs(request).get(pk=job.pk))
        return Response({**payload, "privacy_warnings": privacy_warnings(job.description)})


# --- Worker ----------------------------------------------------------------------------------------------


def _own_invitations(request):
    return Invitation.objects.filter(worker_profile__user=request.user)


@method_decorator(never_cache, name="dispatch")
class InboxView(ListAPIView):
    """GET /invitations/?status=active|declined|withdrawn — invitations addressed to me (paginated)."""

    permission_classes = [IsWorker]

    def get_queryset(self):
        queryset = _own_invitations(self.request).order_by("-created_at")
        wanted = self.request.query_params.get("status")
        if wanted in Invitation.Status.values:
            queryset = queryset.filter(status=wanted)
        return queryset

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([worker_invitation_payload(i) for i in page])


@method_decorator(never_cache, name="dispatch")
class InvitationDetailView(APIView):
    """GET /invitations/{id}/ — mine only; the first open is recorded as ``seen_at``."""

    permission_classes = [IsWorker]

    def get(self, request, invitation_id):
        invitation = _own_invitations(request).filter(pk=invitation_id).first()
        if invitation is None:
            raise NotFound()
        if invitation.seen_at is None:
            invitation.seen_at = timezone.now()
            invitation.save(update_fields=["seen_at"])
        return Response(worker_invitation_payload(invitation))


class DeclineSerializer(StrictFieldsMixin, serializers.Serializer):
    reason = serializers.ChoiceField(choices=Invitation.DeclineReason.choices, required=False, allow_blank=True)


@method_decorator(never_cache, name="dispatch")
class DeclineView(APIView):
    """POST /invitations/{id}/decline/ {reason?} — the targeted worker closes it (idempotent)."""

    permission_classes = [IsWorker]
    throttle_classes = [InvitationThrottle]

    def post(self, request, invitation_id):
        serializer = DeclineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            invitation = _own_invitations(request).select_for_update().filter(pk=invitation_id).first()
            if invitation is None:
                raise NotFound()
            if invitation.status == Invitation.Status.WITHDRAWN:
                raise InvitationClosed()
            if invitation.status == Invitation.Status.ACTIVE:
                invitation.status = Invitation.Status.DECLINED
                invitation.decline_reason = serializer.validated_data.get("reason") or ""
                invitation.closed_at = timezone.now()
                invitation.save(update_fields=["status", "decline_reason", "closed_at"])
        return Response(worker_invitation_payload(invitation))


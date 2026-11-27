"""Booking API (M8). Contracts: docs/api.md § Bookings.

Only the booking's customer and its assigned worker can see or change a booking; anyone else gets 404.
Role-specific actions return 403 ``not_allowed_for_role`` to the other participant. Arrival codes are
returned in plaintext only once, to the customer, by the issue call; they never appear in any other response.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsCustomer
from apps.accounts.serializers import StrictFieldsMixin
from apps.accounts.throttles import ConfigurableRateThrottle
from apps.conversations import quotes as rules
from apps.conversations.views import DraftSerializer
from apps.invitations.views import shared_view
from apps.workers.identity import current_case
from apps.workers.models import IdentityVerification

from . import services
from .models import Booking, BookingChange

_iso = rules.iso_utc


class _PerUserThrottle(ConfigurableRateThrottle):
    def get_cache_key(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS") or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class BookingThrottle(_PerUserThrottle):
    scope = "booking_user"


class CodeIssueThrottle(_PerUserThrottle):
    scope = "arrival_code_issue_user"


class CodeVerifyThrottle(_PerUserThrottle):
    scope = "arrival_code_verify_user"


# --- Payloads -------------------------------------------------------------------------------------------------


def _counterpart(booking: Booking, role: str) -> dict:
    if role == "worker":
        return {"role": "customer"}  # the worker never receives the customer's identity or phone number
    profile = booking.worker_profile
    case = current_case(profile.user)
    verification = case.status if case else None
    return {
        "role": "worker", "worker_id": str(profile.id), "trade": profile.trade.code if profile.trade else None,
        "verification": {"status": verification, "simulated": verification == IdentityVerification.Status.DEMO_APPROVED},
    }


def _code_state(booking: Booking, now) -> dict | None:
    """Whether a code is active — never the code or its digest (both roles see the same)."""
    live = services._live_codes(booking).first()
    if live is None:
        used = booking.arrival_codes.filter(used_at__isnull=False).first()
        return {"active": False, "used_at": _iso(used.used_at)} if used else None
    limit = settings.ARRIVAL_CODE_MAX_ATTEMPTS
    return {"active": now < live.expires_at and live.failed_attempts < limit, "issued_at": _iso(live.issued_at),
            "expires_at": _iso(live.expires_at), "attempts_remaining": max(0, limit - live.failed_attempts),
            "expired": now >= live.expires_at, "locked": live.failed_attempts >= limit, "used_at": None}


def change_payload(change: BookingChange, role: str) -> dict:
    return {
        "id": str(change.id), "number": change.number, "status": change.status, "proposed_role": change.proposed_role,
        "note": change.note, "old_terms": change.old_terms, "new_terms": change.new_terms,
        "customer_approved_at": _iso(change.customer_approved_at), "worker_approved_at": _iso(change.worker_approved_at),
        "decided_at": _iso(change.decided_at), "decided_role": change.decided_role or None, "created_at": _iso(change.created_at),
        "can_approve": change.status == BookingChange.Status.PENDING and change.proposed_role != role,
        "can_withdraw": change.status == BookingChange.Status.PENDING and change.proposed_role == role,
    }


def booking_payload(booking: Booking, role: str, now=None) -> dict:
    now = now or timezone.now()
    reserving = booking.status in Booking.RESERVING
    pending = booking.changes.filter(status=BookingChange.Status.PENDING).exists()
    job = booking.job
    # The exact address: always to its owner; to the assigned worker only while the booking holds their time.
    address = {"address": job.address_private, "access_notes": job.access_notes} if role == "customer" or reserving else None
    return {
        "id": str(booking.id),
        "status": booking.status,
        "role": role,
        "invitation_id": str(booking.invitation_id),
        "job_id": str(booking.job_id) if role == "customer" else None,
        "quote_id": str(booking.quote_id),
        "quote_version": booking.quote_version,
        "start_at": _iso(booking.start_at),
        "end_at": _iso(booking.end_at),
        "timezone": "Asia/Karachi",
        "terms": booking.terms,
        "accepted_terms": booking.accepted_terms,
        "terms_changed": booking.terms.get("source", {}).get("kind") == "change",
        "job": shared_view(booking.invitation.shared_summary),
        "address": address,
        "counterpart": _counterpart(booking, role),
        "created_at": _iso(booking.created_at),
        "arrived_at": _iso(booking.arrived_at),
        "started_at": _iso(booking.started_at),
        "cancelled_at": _iso(booking.cancelled_at),
        "cancelled_role": booking.cancelled_role or None,
        "cancel_reason": booking.cancel_reason or None,
        "cancel_note": booking.cancel_note or None,
        "completion_requested_at": _iso(booking.completion_requested_at),
        "completed_at": _iso(booking.completed_at),
        "completed_services": sorted(s.code for s in booking.completed_services.all()),
        "disputed_at": _iso(booking.disputed_at),
        "dispute_reason": booking.dispute_reason or None,
        "dispute_note": booking.dispute_note or None,
        "closed_at": _iso(booking.closed_at),
        # Staff outcome and reason are shown to both participants (who acted is not: staff stay anonymous).
        "staff_outcome": booking.staff_outcome or None,
        "staff_reason": booking.staff_reason or None,
        "review": _review(booking, role),
        "contact_block": _block(booking, role),
        "arrival_code": _code_state(booking, now),
        "changes": [change_payload(c, role) for c in booking.changes.all()],
        "history": [
            {"kind": e.kind, "from_status": e.from_status or None, "to_status": e.to_status or None,
             "actor_role": e.actor_role or None, "note": e.note or None, "data": e.data, "at": _iso(e.at)}
            for e in booking.events.all()
        ],
        "actions": {
            "arrive": role == "worker" and booking.status == Booking.Status.CONFIRMED,
            "issue_code": role == "customer" and booking.status == Booking.Status.ARRIVED,
            "start": role == "worker" and booking.status == Booking.Status.ARRIVED,
            "cancel": booking.status in Booking.CANCELLABLE,
            "propose_change": booking.status in Booking.CHANGEABLE and not pending,
            "change_time": booking.status == Booking.Status.CONFIRMED,
            "request_completion": role == "worker" and booking.status == Booking.Status.IN_PROGRESS,
            "completion_blocked_by_change": role == "worker" and booking.status == Booking.Status.IN_PROGRESS and pending,
            "confirm_completion": role == "customer" and booking.status == Booking.Status.COMPLETION_REQUESTED,
            "raise_issue": role == "customer" and booking.status == Booking.Status.COMPLETION_REQUESTED,
            "review": role == "customer" and booking.status == Booking.Status.COMPLETED and not booking.reviews.exists(),
        },
    }


def _block(booking: Booking, role: str) -> dict:
    from apps.reports.services import block_state

    me, other = (booking.customer, booking.worker_profile.user) if role == "customer" else (booking.worker_profile.user, booking.customer)
    return block_state(me, other)


def _review(booking: Booking, role: str) -> dict | None:
    """The job's review: always to its author; to the worker only while it is not hidden."""
    from apps.reviews.services import review_payload

    review = booking.reviews.first()
    if review is None or (role == "worker" and review.hidden_at is not None):
        return None
    return review_payload(review, role)


def booking_card(booking: Booking, role: str) -> dict:
    summary = booking.invitation.shared_summary
    return {
        "id": str(booking.id), "status": booking.status, "role": role,
        "start_at": _iso(booking.start_at), "end_at": _iso(booking.end_at),
        "trade": summary.get("trade"), "services": summary.get("services", []), "area": summary.get("area"),
        "known_total": (booking.terms.get("totals") or {}).get("known_total"),
        "complete": (booking.terms.get("totals") or {}).get("complete", False),
        "quote_version": booking.quote_version, "invitation_id": str(booking.invitation_id),
        "worker_id": str(booking.worker_profile_id) if role == "customer" else None,
        "review_submitted": booking.reviews.exists(),
    }


def booking_summary(booking: Booking | None) -> dict | None:
    """Small link used by invitation, conversation and job payloads."""
    return {"id": str(booking.id), "status": booking.status} if booking else None


# --- Views ----------------------------------------------------------------------------------------------------


class AcceptSerializer(StrictFieldsMixin, serializers.Serializer):
    invitation_id = serializers.UUIDField()
    quote_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.UUIDField()


def _mine(request):
    user = request.user
    if user.is_customer:
        return Booking.objects.filter(customer=user), "customer"
    return Booking.objects.filter(worker_profile__user=user), "worker"


@method_decorator(never_cache, name="dispatch")
class BookingsView(ListAPIView):
    """GET /bookings/?status=… — my bookings (customer or worker), newest first · POST — accept a quote."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [BookingThrottle]

    def get_permissions(self):
        return [IsCustomer()] if self.request.method == "POST" else [IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        queryset, role = _mine(request)
        wanted = request.query_params.get("status")
        if wanted in Booking.Status.values:
            queryset = queryset.filter(status=wanted)
        page = self.paginate_queryset(queryset.select_related("invitation").order_by("-start_at"))
        return self.get_paginated_response([booking_card(b, role) for b in page])

    def post(self, request):
        serializer = AcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        booking, created = services.accept_quote(request.user, invitation_id=data["invitation_id"], quote_id=data["quote_id"],
                                                 version=data["version"], key=data["idempotency_key"])
        booking, role = services.participant_booking(request.user, booking.pk)
        return Response({**booking_payload(booking, role), "created": created},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@method_decorator(never_cache, name="dispatch")
class BookingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, booking_id):
        booking, role = services.participant_booking(request.user, booking_id)
        return Response(booking_payload(booking, role))


def _respond(request, booking_id, **extra):
    booking, role = services.participant_booking(request.user, booking_id)
    return Response({**booking_payload(booking, role), **extra})


@method_decorator(never_cache, name="dispatch")
class ArriveView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [BookingThrottle]

    def post(self, request, booking_id):
        services.mark_arrived(request.user, booking_id)
        return _respond(request, booking_id)


@method_decorator(never_cache, name="dispatch")
class IssueCodeView(APIView):
    """POST — the customer reveals a new arrival code. The plaintext is in THIS response only."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [CodeIssueThrottle]

    def post(self, request, booking_id):
        code, row = services.issue_code(request.user, booking_id)
        response = _respond(request, booking_id, code={"value": code, "expires_at": _iso(row.expires_at)})
        response["Cache-Control"] = "no-store"
        return response


class StartSerializer(StrictFieldsMixin, serializers.Serializer):
    code = serializers.CharField(max_length=16, trim_whitespace=True)

    def validate_code(self, value):
        digits = value.replace(" ", "")
        if len(digits) != 6 or not digits.isdigit():
            raise serializers.ValidationError("Enter the 6-digit code.", code="invalid_code_format")
        return digits


@method_decorator(never_cache, name="dispatch")
class StartView(APIView):
    """POST {code} — the assigned worker enters the customer's code; the booking moves to "in progress"."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [CodeVerifyThrottle]

    def post(self, request, booking_id):
        serializer = StartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.start_with_code(request.user, booking_id, serializer.validated_data["code"])
        return _respond(request, booking_id)


class CancelSerializer(StrictFieldsMixin, serializers.Serializer):
    reason = serializers.ChoiceField(choices=Booking.CancelReason.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=500, trim_whitespace=True)

    def validate(self, data):
        if data["reason"] == Booking.CancelReason.OTHER and len(data["note"]) < 3:
            raise serializers.ValidationError({"note": [serializers.ErrorDetail("Say why.", code="required")]})
        return data


@method_decorator(never_cache, name="dispatch")
class CancelView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [BookingThrottle]

    def post(self, request, booking_id):
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel(request.user, booking_id, **serializer.validated_data)
        return _respond(request, booking_id)


class ChangeSerializer(DraftSerializer):
    note = serializers.CharField(min_length=3, max_length=500, trim_whitespace=True)


@method_decorator(never_cache, name="dispatch")
class ChangesView(APIView):
    """POST — propose new terms (full set). They apply only after the other person approves."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [BookingThrottle]

    def post(self, request, booking_id):
        serializer = ChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        note = values.pop("note")
        services.propose_change(request.user, booking_id, values, note)
        return _respond(request, booking_id)


@method_decorator(never_cache, name="dispatch")
class ChangeDecisionView(APIView):
    """POST /changes/{id}/approve|reject|withdraw/."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [BookingThrottle]
    action = "approve"

    def post(self, request, booking_id, change_id):
        services.decide_change(request.user, booking_id, change_id, self.action)
        return _respond(request, booking_id)


# --- Completion, disputes and reviews (M9) ----------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class RequestCompletionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [BookingThrottle]

    def post(self, request, booking_id):
        services.request_completion(request.user, booking_id)
        return _respond(request, booking_id)


@method_decorator(never_cache, name="dispatch")
class ConfirmCompletionView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [BookingThrottle]

    def post(self, request, booking_id):
        services.confirm_completion(request.user, booking_id)
        return _respond(request, booking_id)


class IssueSerializer(StrictFieldsMixin, serializers.Serializer):
    reason = serializers.ChoiceField(choices=Booking.DisputeReason.choices)
    note = serializers.CharField(min_length=3, max_length=500, trim_whitespace=True)


@method_decorator(never_cache, name="dispatch")
class RaiseIssueView(APIView):
    """POST {reason, note} — the customer does not confirm completion; staff review the dispute."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [BookingThrottle]

    def post(self, request, booking_id):
        serializer = IssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.raise_issue(request.user, booking_id, **serializer.validated_data)
        return _respond(request, booking_id)

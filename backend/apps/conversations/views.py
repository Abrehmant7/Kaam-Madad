"""Conversation, quotation and agreement-gap API (M7). Contracts: docs/api.md § Conversations and quotes.

All endpoints live under /conversations/{invitation_id}/ and resolve the caller's role from the
session: the request owner is the "customer", the invited worker is the "worker"; anyone else gets
404. Writes lock the invitation row and re-check that it is still active inside the transaction
(quote submission locks the job first, then the invitation — M6's order).
"""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.exceptions import ErrorDetail, NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import StrictFieldsMixin
from apps.accounts.throttles import ConfigurableRateThrottle
from apps.core.api.exceptions import ApiError
from apps.invitations.models import Invitation
from apps.invitations.views import shared_view
from apps.jobs.models import JobRequest
from apps.voice.models import AudioClip, Purpose, Transcription

from . import quotes as rules
from .models import GapFinding, Message, Quote

logger = logging.getLogger(__name__)
KARACHI = ZoneInfo("Asia/Karachi")
PAGE = 30


class ConversationThrottle(ConfigurableRateThrottle):
    scope = "conversation_user"

    def get_cache_key(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS") or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class ConversationClosed(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conversation_closed"
    default_detail = "This invitation is closed. The conversation is read-only."


class WorkerOnly(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "worker_only"
    default_detail = "Only the invited worker can do this."


class CustomerOnly(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "customer_only"
    default_detail = "Only the customer can do this."


class NoDraft(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "no_quote_draft"
    default_detail = "There is no quote draft to submit."


class QuoteNotCurrent(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "quote_not_current"
    default_detail = "This quote version is no longer the current one."


class CheckNotNeeded(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "check_not_needed"
    default_detail = "This action is not needed for this quote."


# --- Participants -----------------------------------------------------------------------------------------


def role_in(invitation: Invitation, user) -> str | None:
    if invitation.job.customer_id == user.pk:
        return "customer"
    if invitation.worker_profile.user_id == user.pk:
        return "worker"
    return None


def participation(request, invitation_id, *, lock: bool = False) -> tuple[Invitation, str]:
    queryset = Invitation.objects.select_related("job", "worker_profile__trade", "worker_profile__user")
    if lock:
        queryset = Invitation.objects.select_for_update()
    invitation = queryset.filter(pk=invitation_id).first()
    if invitation is None:
        raise NotFound()
    role = role_in(invitation, request.user)
    if role is None:
        raise NotFound()  # never reveal another pair's conversation
    return invitation, role


def require_active(invitation: Invitation) -> None:
    if invitation.status != Invitation.Status.ACTIVE:
        raise ConversationClosed()


# --- Payloads -------------------------------------------------------------------------------------------------


_iso = rules.iso_utc


def header_payload(invitation: Invitation, role: str) -> dict:
    profile = invitation.worker_profile
    return {
        "invitation": {"id": str(invitation.id), "status": invitation.status, "created_at": _iso(invitation.created_at),
                       "closed_at": _iso(invitation.closed_at)},
        "role": role,
        "can_write": invitation.status == Invitation.Status.ACTIVE,
        "job": shared_view(invitation.shared_summary),
        # Only the owner gets the request ID (for the link back to their request); the worker never does.
        "job_id": str(invitation.job_id) if role == "customer" else None,
        # The customer sees the worker's opaque reference; the worker never sees the customer's identity.
        "counterpart": {"role": "worker", "worker_id": str(profile.id), "trade": profile.trade.code if profile.trade else None}
        if role == "customer" else {"role": "customer"},
    }


def message_payload(message: Message, viewer) -> dict:
    mine = message.sender_id == viewer.pk
    return {
        "id": str(message.id),
        "client_id": str(message.client_id) if mine else None,
        "sender_role": message.sender_role,
        "mine": mine,
        "kind": message.kind,
        "text": message.text,
        "caption_status": message.caption_status or None,
        # The automatic proposal is shown to its sender only; the other side sees the approved caption.
        "interpreted_text": message.interpreted_text if mine and message.interpreted_text else None,
        "audio_url": f"/api/v1/conversations/{message.invitation_id}/messages/{message.id}/audio/" if message.audio_clip_id else None,
        "duration_seconds": float(message.audio_clip.duration_seconds) if message.audio_clip_id else None,
        "created_at": _iso(message.created_at),
    }


def finding_payload(finding: GapFinding) -> dict:
    return {
        "id": str(finding.id), "source": finding.source, "code": finding.code, "blocking": finding.blocking,
        "question": finding.question, "ask": finding.ask, "sources": finding.sources, "status": finding.status,
        "resolution": finding.resolution or None, "resolution_note": finding.resolution_note or None,
        "resolved_role": finding.resolved_role or None, "resolved_at": _iso(finding.resolved_at),
    }


def _money(value):
    return str(value) if value is not None else None


def quote_payload(quote: Quote, now=None) -> dict:
    now = now or timezone.now()
    draft = quote.status == Quote.Status.DRAFT
    return {
        "id": str(quote.id),
        "version": quote.version,
        "status": quote.status,
        "inspection_only": quote.inspection_only,
        "scope": quote.scope,
        "quantity": quote.quantity,
        "labour_amount": _money(quote.labour_amount),
        "labour_basis": quote.labour_basis,
        "materials": quote.materials or None,
        "materials_amount": _money(quote.materials_amount),
        "visit_fee": _money(quote.visit_fee),
        "visit_fee_treatment": quote.visit_fee_treatment,
        "exclusions": quote.exclusions,
        "start_at": _iso(quote.start_at),
        "end_at": _iso(quote.end_at),
        "timezone": "Asia/Karachi",
        "totals": rules.compute_totals(quote) if draft else quote.totals,
        "submitted_at": _iso(quote.submitted_at),
        "superseded_at": _iso(quote.superseded_at),
        "expires_at": _iso(quote.expires_at),
        "expired": bool(quote.expires_at and now >= quote.expires_at),
        "check": {"status": quote.check_status, "provider": quote.check_provider or None, "simulated": quote.check_simulated,
                  "checked_at": _iso(quote.checked_at),
                  "failure": quote.check_failure.split(":")[0] if quote.check_failure else None},
        "manual_review_at": _iso(quote.manual_review_at),
        "findings": [finding_payload(f) for f in quote.findings.all()],
        "issues": {name: [code for code, _ in items] for name, items in rules.validate(quote, now).items()} if draft else {},
    }


# --- Conversation ---------------------------------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class ConversationView(APIView):
    """GET /conversations/{invitation_id}/ — header: role, status, whether writing is allowed, shared job."""

    permission_classes = [IsAuthenticated]

    def get(self, request, invitation_id):
        invitation, role = participation(request, invitation_id)
        return Response(header_payload(invitation, role))


class SendSerializer(StrictFieldsMixin, serializers.Serializer):
    client_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=Message.Kind.choices)
    text = serializers.CharField(required=False, allow_blank=True, max_length=1000, trim_whitespace=True)
    audio_clip_id = serializers.UUIDField(required=False)
    transcription_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if data["kind"] == "text" and not data.get("text"):
            raise serializers.ValidationError({"text": [ErrorDetail("Write a message.", code="required")]})
        if data["kind"] == "voice" and not data.get("audio_clip_id"):
            raise serializers.ValidationError({"audio_clip_id": [ErrorDetail("Record a voice note.", code="required")]})
        if data["kind"] == "text" and (data.get("audio_clip_id") or data.get("transcription_id")):
            raise serializers.ValidationError({"kind": [ErrorDetail("A text message has no audio.", code="invalid")]})
        return data


def _page(queryset, request):
    after, before = request.query_params.get("after"), request.query_params.get("before")

    def anchor(message_id):
        message = queryset.filter(pk=message_id).first() if message_id else None
        if message_id and message is None:
            raise ValidationError({"cursor": [ErrorDetail("Unknown message.", code="invalid")]})
        return message

    if after:
        ref = anchor(after)
        items = list(queryset.filter(Q(created_at__gt=ref.created_at) | Q(created_at=ref.created_at, id__gt=ref.id))
                     .order_by("created_at", "id")[:100])
        return items, None
    newest_first = queryset.order_by("-created_at", "-id")
    if before:
        ref = anchor(before)
        newest_first = newest_first.filter(Q(created_at__lt=ref.created_at) | Q(created_at=ref.created_at, id__lt=ref.id))
    chunk = list(newest_first[:PAGE + 1])
    has_more = len(chunk) > PAGE
    return list(reversed(chunk[:PAGE])), has_more


@method_decorator(never_cache, name="dispatch")
class MessagesView(APIView):
    """GET ?after=<id> (poll) | ?before=<id> (older) | latest page · POST send (idempotent per client_id)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ConversationThrottle]

    def get(self, request, invitation_id):
        invitation, _ = participation(request, invitation_id)
        queryset = Message.objects.filter(invitation=invitation).select_related("audio_clip")
        items, has_more = _page(queryset, request)
        return Response({"results": [message_payload(m, request.user) for m in items], "has_more_before": has_more})

    def post(self, request, invitation_id):
        serializer = SendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            invitation, role = participation(request, invitation_id, lock=True)
            existing = Message.objects.filter(invitation=invitation, sender=request.user, client_id=data["client_id"]).first()
            if existing:
                return Response(message_payload(existing, request.user), status=status.HTTP_200_OK)  # a retry
            require_active(invitation)
            message = Message(invitation=invitation, sender=request.user, sender_role=role, client_id=data["client_id"],
                              kind=data["kind"], text=data.get("text", ""))
            if data["kind"] == "voice":
                clip = AudioClip.objects.filter(pk=data["audio_clip_id"], owner=request.user, purpose=Purpose.MESSAGE).first()
                if clip is None or Message.objects.filter(audio_clip=clip).exists():
                    raise ValidationError({"audio_clip_id": [ErrorDetail("Voice note not found.", code="not_found")]})
                message.audio_clip = clip
                if data.get("transcription_id"):
                    transcription = Transcription.objects.filter(pk=data["transcription_id"], clip=clip).first()
                    if transcription is None:
                        raise ValidationError({"transcription_id": [ErrorDetail("Not found.", code="not_found")]})
                    message.transcription = transcription
                    message.interpreted_text = transcription.text
                if message.text:
                    message.caption_status = (
                        Message.CaptionStatus.APPROVED if message.transcription_id else Message.CaptionStatus.TYPED
                    )
                else:
                    message.caption_status = Message.CaptionStatus.UNAVAILABLE
            try:
                with transaction.atomic():
                    message.save()
            except IntegrityError:
                existing = Message.objects.filter(invitation=invitation, sender=request.user, client_id=data["client_id"]).first()
                if existing:
                    return Response(message_payload(existing, request.user), status=status.HTTP_200_OK)
                raise
        logger.info("Message sent (kind=%s).", message.kind)
        return Response(message_payload(message, request.user), status=status.HTTP_201_CREATED)


class MessageAudioView(APIView):
    """GET — the original voice note, for the two participants only; never cached."""

    permission_classes = [IsAuthenticated]

    def get(self, request, invitation_id, message_id):
        invitation, _ = participation(request, invitation_id)
        message = Message.objects.filter(pk=message_id, invitation=invitation, audio_clip__isnull=False).select_related("audio_clip").first()
        if message is None:
            raise NotFound()
        clip = message.audio_clip
        response = FileResponse(clip.file.open("rb"), content_type=clip.mime_type)
        response["Content-Disposition"] = 'inline; filename="voice-note"'
        response["Cache-Control"] = "private, no-store"
        return response


# --- Quotes -------------------------------------------------------------------------------------------------------


class DraftSerializer(StrictFieldsMixin, serializers.Serializer):
    inspection_only = serializers.BooleanField(default=False)
    scope = serializers.CharField(allow_blank=True, max_length=1000, trim_whitespace=True)
    # Storage bounds only; the 1–999 rule is checked on submit as "quantity_out_of_range".
    quantity = serializers.IntegerField(allow_null=True, required=False, min_value=0, max_value=32767)
    labour_amount = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False, min_value=0)
    labour_basis = serializers.ChoiceField(choices=Quote.LabourBasis.choices, default=Quote.LabourBasis.TOTAL)
    materials = serializers.ChoiceField(choices=Quote.Materials.choices, allow_blank=True, required=False, default="")
    materials_amount = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False, min_value=0)
    visit_fee = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False, min_value=0)
    visit_fee_treatment = serializers.ChoiceField(choices=Quote.VisitFee.choices, default=Quote.VisitFee.NONE)
    exclusions = serializers.CharField(allow_blank=True, required=False, default="", max_length=500, trim_whitespace=True)
    start_at = serializers.DateTimeField(allow_null=True, required=False, default_timezone=KARACHI)
    end_at = serializers.DateTimeField(allow_null=True, required=False, default_timezone=KARACHI)


def _raise(errors: dict) -> None:
    raise ValidationError({name: [ErrorDetail(message, code=code) for code, message in items] for name, items in errors.items()})


@method_decorator(never_cache, name="dispatch")
class QuotesView(APIView):
    """GET — current version, the worker's draft (worker only), superseded history, readiness."""

    permission_classes = [IsAuthenticated]

    def get(self, request, invitation_id):
        invitation, role = participation(request, invitation_id)
        submitted = list(invitation.quotes.exclude(status=Quote.Status.DRAFT).prefetch_related("findings").order_by("-version"))
        current = next((q for q in submitted if q.status == Quote.Status.SUBMITTED), None)
        draft = invitation.quotes.filter(status=Quote.Status.DRAFT).first() if role == "worker" else None
        return Response({
            "current": quote_payload(current) if current else None,
            "draft": quote_payload(draft) if draft else None,
            "history": [quote_payload(q) for q in submitted if q.status == Quote.Status.SUPERSEDED],
            "readiness": rules.readiness(invitation, current),
        })


@method_decorator(never_cache, name="dispatch")
class QuoteDraftView(APIView):
    """PUT /quotes/draft/ — the worker saves the draft (replaces all fields) · DELETE — discard it."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ConversationThrottle]

    def put(self, request, invitation_id):
        serializer = DraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            invitation, role = participation(request, invitation_id, lock=True)
            if role != "worker":
                raise WorkerOnly()
            require_active(invitation)
            draft = invitation.quotes.select_for_update().filter(status=Quote.Status.DRAFT).first() or Quote(invitation=invitation)
            for name, value in serializer.validated_data.items():
                setattr(draft, name, value)
            draft.save()
        return Response(quote_payload(draft))

    def delete(self, request, invitation_id):
        with transaction.atomic():
            invitation, role = participation(request, invitation_id, lock=True)
            if role != "worker":
                raise WorkerOnly()
            invitation.quotes.filter(status=Quote.Status.DRAFT).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def submit_draft(invitation_id, user) -> Quote:
    """Freeze the worker's draft as the next version. Safe against concurrent closure of the invitation."""
    with transaction.atomic():
        invitation = Invitation.objects.select_related("job").filter(pk=invitation_id).first()
        if invitation is None or invitation.worker_profile.user_id != user.pk:
            raise NotFound()
        JobRequest.objects.select_for_update().get(pk=invitation.job_id)            # 1. job (M6 order)
        invitation = Invitation.objects.select_for_update().get(pk=invitation_id)  # 2. invitation, re-read
        require_active(invitation)
        draft = invitation.quotes.select_for_update().filter(status=Quote.Status.DRAFT).first()
        if draft is None:
            raise NoDraft()
        now = timezone.now()
        errors = rules.validate(draft, now)
        if errors:
            _raise(errors)
        previous = invitation.quotes.select_for_update().filter(status=Quote.Status.SUBMITTED).first()
        if previous:
            previous.status, previous.superseded_at = Quote.Status.SUPERSEDED, now
            previous.save(update_fields=["status", "superseded_at", "updated_at"])
        last = invitation.quotes.exclude(version__isnull=True).order_by("-version").values_list("version", flat=True).first()
        draft.version = (last or 0) + 1
        draft.status = Quote.Status.SUBMITTED
        draft.submitted_at = now
        draft.expires_at = rules.expiry_for(now, draft.start_at)
        draft.totals = rules.compute_totals(draft)
        draft.save()
        draft.invitation = invitation
        for finding in rules.rule_findings(draft):
            GapFinding.objects.create(quote=draft, source=GapFinding.Source.RULE, **finding)
    logger.info("Quote version submitted.")
    return draft


@method_decorator(never_cache, name="dispatch")
class QuoteSubmitView(APIView):
    """POST /quotes/draft/submit/ — freeze the draft as a new version, then run the agreement check."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ConversationThrottle]

    def post(self, request, invitation_id):
        invitation, role = participation(request, invitation_id)
        if role != "worker":
            raise WorkerOnly()
        quote = submit_draft(invitation_id, request.user)
        rules.run_ai_check(quote)  # outside the transaction; failure is recorded as "unavailable"
        quote.refresh_from_db()
        return Response(quote_payload(quote), status=status.HTTP_201_CREATED)


def _current_quote_for(request, invitation_id, quote_id, *, lock=False) -> tuple[Invitation, str, Quote]:
    invitation, role = participation(request, invitation_id, lock=lock)
    queryset = invitation.quotes.select_for_update() if lock else invitation.quotes
    quote = queryset.filter(pk=quote_id).exclude(status=Quote.Status.DRAFT).first()
    if quote is None:
        raise NotFound()
    return invitation, role, quote


@method_decorator(never_cache, name="dispatch")
class QuoteDetailView(APIView):
    """GET /quotes/{id}/ — any submitted or superseded version (both participants)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, invitation_id, quote_id):
        invitation, _, quote = _current_quote_for(request, invitation_id, quote_id)
        return Response({**quote_payload(quote), "readiness": rules.readiness(invitation, quote)})


@method_decorator(never_cache, name="dispatch")
class QuoteCheckView(APIView):
    """POST /quotes/{id}/check/ — run the automated check again (only when it has not run or could not run)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ConversationThrottle]

    def post(self, request, invitation_id, quote_id):
        invitation, _, quote = _current_quote_for(request, invitation_id, quote_id)
        require_active(invitation)
        if quote.status != Quote.Status.SUBMITTED:
            raise QuoteNotCurrent()
        if quote.check_status not in (Quote.CheckStatus.NOT_RUN, Quote.CheckStatus.UNAVAILABLE):
            raise CheckNotNeeded()
        rules.run_ai_check(quote)
        quote.refresh_from_db()
        return Response({**quote_payload(quote), "readiness": rules.readiness(invitation, quote)})


class ResolveSerializer(StrictFieldsMixin, serializers.Serializer):
    resolution = serializers.ChoiceField(choices=GapFinding.Resolution.choices)
    note = serializers.CharField(min_length=3, max_length=500, trim_whitespace=True)


@method_decorator(never_cache, name="dispatch")
class FindingResolveView(APIView):
    """POST /quotes/{id}/findings/{finding_id}/resolve/ {resolution, note} — record an explicit clarification
    (who, when, the corrected terms). A finding cannot be dismissed without a note."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ConversationThrottle]

    def post(self, request, invitation_id, quote_id, finding_id):
        serializer = ResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            invitation, role, quote = _current_quote_for(request, invitation_id, quote_id, lock=True)
            require_active(invitation)
            if quote.status != Quote.Status.SUBMITTED:
                raise QuoteNotCurrent()
            finding = quote.findings.select_for_update().filter(pk=finding_id).first()
            if finding is None:
                raise NotFound()
            if finding.status == GapFinding.Status.OPEN:
                finding.status = GapFinding.Status.RESOLVED
                finding.resolution = serializer.validated_data["resolution"]
                finding.resolution_note = serializer.validated_data["note"]
                finding.resolved_by, finding.resolved_role, finding.resolved_at = request.user, role, timezone.now()
                finding.save()
        return Response({**quote_payload(quote), "readiness": rules.readiness(invitation, quote)})


@method_decorator(never_cache, name="dispatch")
class ManualReviewView(APIView):
    """POST /quotes/{id}/manual-review/ — when the automated check could not run, the customer confirms they
    reviewed the terms themselves. Recorded as such; never shown as a successful automated check."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ConversationThrottle]

    def post(self, request, invitation_id, quote_id):
        with transaction.atomic():
            invitation, role, quote = _current_quote_for(request, invitation_id, quote_id, lock=True)
            if role != "customer":
                raise CustomerOnly()
            require_active(invitation)
            if quote.status != Quote.Status.SUBMITTED:
                raise QuoteNotCurrent()
            if quote.check_status != Quote.CheckStatus.UNAVAILABLE:
                raise CheckNotNeeded()
            if quote.manual_review_at is None:
                quote.manual_review_by, quote.manual_review_at = request.user, timezone.now()
                quote.save(update_fields=["manual_review_by", "manual_review_at", "updated_at"])
        return Response({**quote_payload(quote), "readiness": rules.readiness(invitation, quote)})


@method_decorator(never_cache, name="dispatch")
class ReadinessView(APIView):
    """GET /conversations/{invitation_id}/readiness/ — M8 hand-off for the current quote."""

    permission_classes = [IsAuthenticated]

    def get(self, request, invitation_id):
        invitation, _ = participation(request, invitation_id)
        return Response(rules.readiness(invitation))

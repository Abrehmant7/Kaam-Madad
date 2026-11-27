"""Report and block API (M10). Contracts: docs/api.md § Reports, moderation and blocks.

Only the reporter can read a report or download its evidence. The reported user, other users and staff in the
API get 404 (staff use Django Admin, where evidence access needs its own permission and is recorded).
"""

from __future__ import annotations

import os

from django.http import FileResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import StrictFieldsMixin
from apps.accounts.throttles import ConfigurableRateThrottle
from apps.conversations.quotes import iso_utc
from apps.jobs.photos import MAX_BYTES, PhotoTooLarge

from . import services
from .models import Report, ReportEvidence, ReportMessage

_iso = iso_utc


class ReportThrottle(ConfigurableRateThrottle):
    scope = "report_user"

    def get_cache_key(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS") or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


def evidence_payload(item: ReportEvidence) -> dict:
    return {
        "id": str(item.id), "kind": item.kind, "role": item.role, "mime_type": item.mime_type, "size_bytes": item.size_bytes,
        "created_at": _iso(item.created_at), "removed": item.deleted_at is not None,
        "content_url": None if item.deleted_at else f"/api/v1/reports/{item.report_id}/evidence/{item.id}/content/",
    }


def report_payload(report: Report, full: bool = True) -> dict:
    payload = {
        "id": str(report.id), "status": report.status, "category": report.category, "reporter_role": report.reporter_role,
        "interaction": {"invitation_id": str(report.invitation_id), "booking_id": str(report.booking_id) if report.booking_id else None},
        "awaiting_reply": report.awaiting_reply, "created_at": _iso(report.created_at), "updated_at": _iso(report.updated_at),
        "closed_at": _iso(report.closed_at),
    }
    if full:
        payload["description"] = report.description
        payload["evidence"] = [evidence_payload(e) for e in report.evidence.all()]
        # Only the reporter's replies and staff messages INTENDED for the reporter; internal notes never leave Admin.
        payload["messages"] = [
            {"from": "you" if m.kind == ReportMessage.Kind.REPORTER_REPLY else "staff", "text": m.text, "at": _iso(m.created_at)}
            for m in report.messages.exclude(kind=ReportMessage.Kind.INTERNAL)
        ]
        payload["can_reply"] = report.status not in Report.CLOSED
        payload["can_add_evidence"] = report.status not in Report.CLOSED and \
            report.evidence.filter(role=ReportEvidence.Role.EVIDENCE).count() < services.MAX_EVIDENCE
    return payload


class FileSerializer(StrictFieldsMixin, serializers.Serializer):
    invitation_id = serializers.UUIDField(required=False)
    booking_id = serializers.UUIDField(required=False)
    client_id = serializers.UUIDField()
    category = serializers.ChoiceField(choices=Report.Category.choices)
    description = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000, trim_whitespace=True)
    audio_clip_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if bool(data.get("invitation_id")) == bool(data.get("booking_id")):
            raise serializers.ValidationError({"non_field_errors": [serializers.ErrorDetail("Give one interaction.", code="invalid")]})
        return data


@method_decorator(never_cache, name="dispatch")
class ReportsView(ListAPIView):
    """GET /reports/ — my reports (newest first) · POST — file a report about the other participant."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ReportThrottle]

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(Report.objects.filter(reporter=request.user).order_by("-created_at"))
        return self.get_paginated_response([report_payload(r, full=False) for r in page])

    def post(self, request):
        serializer = FileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report, created = services.file_report(request.user, **serializer.validated_data)
        return Response({**report_payload(report), "created": created}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@method_decorator(never_cache, name="dispatch")
class ReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, report_id):
        return Response(report_payload(services.own_report(request.user, report_id)))


class AudioEvidenceSerializer(StrictFieldsMixin, serializers.Serializer):
    audio_clip_id = serializers.UUIDField()


@method_decorator(never_cache, name="dispatch")
class EvidenceView(APIView):
    """POST multipart {file: image} or JSON {audio_clip_id} — add evidence to my open report (max 5)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ReportThrottle]
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request, report_id):
        upload = request.FILES.get("file")
        if upload is not None:
            if upload.size > MAX_BYTES or int(request.META.get("CONTENT_LENGTH") or 0) > MAX_BYTES + 64 * 1024:
                raise PhotoTooLarge(details={"max_bytes": MAX_BYTES})
            services.add_evidence(request.user, report_id, image=upload.read())
        else:
            serializer = AudioEvidenceSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            services.add_evidence(request.user, report_id, audio_clip_id=serializer.validated_data["audio_clip_id"])
        return Response(report_payload(services.own_report(request.user, report_id)), status=status.HTTP_201_CREATED)


def evidence_file_response(item: ReportEvidence) -> FileResponse:
    if item.kind == ReportEvidence.Kind.AUDIO:
        if item.audio_clip is None:
            raise NotFound()
        handle, name = item.audio_clip.file, f"evidence{os.path.splitext(item.audio_clip.file.name)[1]}"
    else:
        handle, name = item.file, f"evidence{os.path.splitext(item.file.name)[1]}"
    response = FileResponse(handle.open("rb"), content_type=item.mime_type)
    response["Content-Disposition"] = f'inline; filename="{name}"'
    response["Cache-Control"] = "private, no-store"
    return response


class EvidenceContentView(APIView):
    """GET — the reporter's own evidence only (everyone else 404)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, report_id, evidence_id):
        report = services.own_report(request.user, report_id)
        item = report.evidence.select_related("audio_clip").filter(pk=evidence_id, deleted_at__isnull=True).first()
        if item is None:
            raise NotFound()
        return evidence_file_response(item)


class ReplySerializer(StrictFieldsMixin, serializers.Serializer):
    text = serializers.CharField(min_length=2, max_length=2000, trim_whitespace=True)


@method_decorator(never_cache, name="dispatch")
class ReplyView(APIView):
    """POST {text} — the reporter adds information (e.g. after staff asked for more)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ReportThrottle]

    def post(self, request, report_id):
        serializer = ReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.add_reply(request.user, report_id, serializer.validated_data["text"])
        return Response(report_payload(services.own_report(request.user, report_id)), status=status.HTTP_201_CREATED)


# --- Blocks ---------------------------------------------------------------------------------------------------


class BlockSerializer(StrictFieldsMixin, serializers.Serializer):
    invitation_id = serializers.UUIDField(required=False)
    booking_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if bool(data.get("invitation_id")) == bool(data.get("booking_id")):
            raise serializers.ValidationError({"non_field_errors": [serializers.ErrorDetail("Give one interaction.", code="invalid")]})
        return data


@method_decorator(never_cache, name="dispatch")
class BlocksView(APIView):
    """POST {invitation_id | booking_id} — block further contact with the other participant."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ReportThrottle]

    def post(self, request):
        serializer = BlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        block = services.block(request.user, **serializer.validated_data)
        return Response({"id": str(block.id), "created_at": _iso(block.created_at)}, status=status.HTTP_201_CREATED)


@method_decorator(never_cache, name="dispatch")
class BlockDetailView(APIView):
    """DELETE — lift my own block."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, block_id):
        services.unblock(request.user, block_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


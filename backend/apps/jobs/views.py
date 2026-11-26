"""Customer job request API (M5). Contracts: docs/api.md § Job requests.

Every endpoint requires a signed-in CUSTOMER and only ever looks up that customer's own rows
(other customers' IDs → 404; workers → 403). Ownership of attached audio, transcriptions and
interpretations is derived from the session, never from the request body.
"""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.exceptions import ErrorDetail, NotFound, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsCustomer
from apps.accounts.serializers import StrictFieldsMixin
from apps.accounts.throttles import ConfigurableRateThrottle
from apps.catalog.models import Area, City, ServiceTag, Trade
from apps.core.api.exceptions import ApiError
from apps.voice import drafts
from apps.voice.models import AudioClip, Interpretation, Purpose, Transcription

from . import photos as photo_rules
from . import rules
from .models import JobPhoto, JobRequest

logger = logging.getLogger(__name__)
KARACHI = ZoneInfo("Asia/Karachi")


class JobsThrottle(ConfigurableRateThrottle):
    scope = "jobs_user"

    def get_cache_key(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS") or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class NotEditable(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "request_not_editable"
    default_detail = "A confirmed request can no longer be changed."


class SourceMismatch(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "request_source_mismatch"
    default_detail = "This voice note or text belongs to a different description."


# --- Payloads ------------------------------------------------------------------------------------


def _iso(value):
    return value.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z") if value else None


def state_of(job: JobRequest) -> rules.State:
    return rules.State(
        description=job.description,
        trade=job.trade.code if job.trade else None,
        services=sorted(s.code for s in job.services.all()),
        services_excluded=sorted(s.code for s in job.services_excluded.all()),
        city=job.city.code if job.city else None,
        area=job.area.code if job.area else None,
        preferred_time_text=job.preferred_time_text,
        window_start=job.window_start,
        window_end=job.window_end,
        address_private=job.address_private,
        access_notes=job.access_notes,
        budget_pkr=job.budget_pkr,
    )


def photo_payload(photo: JobPhoto) -> dict:
    return {
        "id": str(photo.id), "mime_type": photo.mime_type, "width": photo.width, "height": photo.height,
        "size_bytes": photo.size_bytes,
        "content_url": f"/api/v1/jobs/{photo.job_id}/photos/{photo.id}/content/",
    }


def suggestions_payload(job: JobRequest) -> dict | None:
    interpretation = job.interpretation
    if interpretation is None:
        return None
    draft = interpretation.draft
    return {
        "interpretation_id": str(interpretation.id),
        "provider": interpretation.provider,
        "simulated": interpretation.simulated,
        "fields": drafts.effective_fields(draft, interpretation.corrections),
        "missing": draft.get("missing", []),
        "uncertain": draft.get("uncertain", []),
        "unmatched_mentions": draft.get("unmatched_mentions", []),
        "heard": draft.get("heard", {}),
    }


def job_payload(job: JobRequest) -> dict:
    state = state_of(job)
    issues = rules.check(state, complete=True) if job.status == JobRequest.Status.DRAFT else {}
    return {
        "id": str(job.id),
        "status": job.status,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
        "confirmed_at": _iso(job.confirmed_at),
        "source": {
            "kind": job.source_kind,
            "language": job.source_language or None,
            # Untouched original input (typed text or transcript), including negations.
            "original_text": job.original_text,
            "audio_clip_id": str(job.audio_clip_id) if job.audio_clip_id else None,
            "transcription_id": str(job.transcription_id) if job.transcription_id else None,
        },
        "details": {
            "description": state.description,
            "trade": state.trade,
            "services": state.services,
            "services_excluded": state.services_excluded,
            "city": state.city,
            "area": state.area,
            "preferred_time_text": state.preferred_time_text,
            "window_start": _iso(state.window_start),
            "window_end": _iso(state.window_end),
            "timezone": "Asia/Karachi",
            "address_private": state.address_private,
            "access_notes": state.access_notes,
            "budget_pkr": str(state.budget_pkr) if state.budget_pkr is not None else None,
        },
        "suggestions": suggestions_payload(job),
        "photos": [photo_payload(photo) for photo in job.photos.all()],
        "issues": {name: [code for code, _ in items] for name, items in issues.items()},
        "ready_to_confirm": job.status == JobRequest.Status.DRAFT and not issues,
    }


def list_payload(job: JobRequest) -> dict:
    return {
        "id": str(job.id),
        "status": job.status,
        "description": (job.description or job.original_text)[:160],
        "trade": job.trade.code if job.trade else None,
        "services": sorted(s.code for s in job.services.all()),
        "city": job.city.code if job.city else None,
        "area": job.area.code if job.area else None,
        "window_start": _iso(job.window_start),
        "window_end": _iso(job.window_end),
        "updated_at": _iso(job.updated_at),
        "confirmed_at": _iso(job.confirmed_at),
    }


def _raise(errors: dict) -> None:
    raise ValidationError({name: [ErrorDetail(message, code=code) for code, message in items] for name, items in errors.items()})


def own_jobs(request):
    return (
        JobRequest.objects.filter(customer=request.user)
        .select_related("trade", "city", "area", "interpretation")
        .prefetch_related("services", "services_excluded", "photos")
    )


def get_own_job(request, job_id, *, lock: bool = False) -> JobRequest:
    queryset = JobRequest.objects.filter(customer=request.user)
    if lock:
        queryset = queryset.select_for_update()
    job = queryset.filter(pk=job_id).first()
    if job is None:
        raise NotFound()
    return job


# --- Serializers -----------------------------------------------------------------------------------


class CreateSerializer(StrictFieldsMixin, serializers.Serializer):
    source_kind = serializers.ChoiceField(choices=JobRequest.SourceKind.choices)
    source_language = serializers.ChoiceField(choices=["ur", "en"], required=False, default="ur")
    original_text = serializers.CharField(required=False, allow_blank=True, max_length=rules.MAX_DESCRIPTION, trim_whitespace=True)
    audio_clip_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if data["source_kind"] == "text" and not data.get("original_text"):
            raise serializers.ValidationError({"original_text": [ErrorDetail("Describe the job.", code="required")]})
        if data["source_kind"] == "voice" and not data.get("audio_clip_id"):
            raise serializers.ValidationError({"audio_clip_id": [ErrorDetail("Record or upload a voice note.", code="required")]})
        return data


class CodeList(serializers.ListField):
    def __init__(self, **kwargs):
        super().__init__(child=serializers.SlugField(max_length=64), allow_empty=True, max_length=30, **kwargs)


class DetailsSerializer(StrictFieldsMixin, serializers.Serializer):
    """Partial update of a draft. Naive times are read as Asia/Karachi; all are stored in UTC."""

    description = serializers.CharField(required=False, allow_blank=True, max_length=rules.MAX_DESCRIPTION, trim_whitespace=True)
    trade = serializers.SlugField(required=False, allow_null=True, max_length=64)
    services = CodeList(required=False)
    services_excluded = CodeList(required=False)
    city = serializers.SlugField(required=False, allow_null=True, max_length=64)
    area = serializers.SlugField(required=False, allow_null=True, max_length=64)
    preferred_time_text = serializers.CharField(required=False, allow_blank=True, max_length=120, trim_whitespace=True)
    window_start = serializers.DateTimeField(required=False, allow_null=True, default_timezone=KARACHI)
    window_end = serializers.DateTimeField(required=False, allow_null=True, default_timezone=KARACHI)
    address_private = serializers.CharField(required=False, allow_blank=True, max_length=rules.MAX_PRIVATE_TEXT, trim_whitespace=True)
    access_notes = serializers.CharField(required=False, allow_blank=True, max_length=rules.MAX_PRIVATE_TEXT, trim_whitespace=True)
    budget_pkr = serializers.DecimalField(
        required=False, allow_null=True, max_digits=10, decimal_places=2, min_value=0, max_value=10_000_000,
    )


class SourceSerializer(StrictFieldsMixin, serializers.Serializer):
    transcription_id = serializers.UUIDField(required=False)
    interpretation_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if not data:
            raise serializers.ValidationError("Provide a transcription or an interpretation.", code="required")
        return data


# --- Applying state -----------------------------------------------------------------------------------


def apply_state(job: JobRequest, state: rules.State) -> None:
    job.description = state.description
    job.trade = Trade.objects.get(code=state.trade) if state.trade else None
    job.city = City.objects.get(code=state.city) if state.city else None
    job.area = Area.objects.get(code=state.area) if state.area else None
    job.preferred_time_text = state.preferred_time_text
    job.window_start, job.window_end = state.window_start, state.window_end
    job.address_private, job.access_notes = state.address_private, state.access_notes
    job.budget_pkr = state.budget_pkr
    job.save()
    job.services.set(ServiceTag.objects.filter(code__in=state.services))
    job.services_excluded.set(ServiceTag.objects.filter(code__in=state.services_excluded))


def prefill_from(job: JobRequest, interpretation: Interpretation) -> None:
    """Copy AI suggestions into EMPTY fields only; only active catalog entries that fit together."""
    fields = drafts.effective_fields(interpretation.draft, interpretation.corrections)
    state = state_of(job)
    if not state.description and fields.get("description"):
        state.description = str(fields["description"])[: rules.MAX_DESCRIPTION]
    suggested = list(ServiceTag.objects.filter(code__in=fields.get("services") or [], is_active=True, trade__is_active=True))
    excluded = list(ServiceTag.objects.filter(code__in=fields.get("services_excluded") or [], is_active=True))
    trade = Trade.objects.filter(code=fields.get("trade"), is_active=True).first() if fields.get("trade") else None
    if trade is None and suggested and len({s.trade_id for s in suggested}) == 1:
        trade = suggested[0].trade  # e.g. "fan installation" implies electrician
    if not state.trade and trade:
        state.trade = trade.code
    if state.trade and not state.services:
        state.services = [s.code for s in suggested if s.trade.code == state.trade]
    if state.trade and not state.services_excluded:
        state.services_excluded = [
            s.code for s in excluded if s.trade.code == state.trade and s.code not in state.services
        ]
    area = Area.objects.filter(code=fields.get("area"), is_active=True, city__is_active=True).select_related("city").first() \
        if fields.get("area") else None
    if area and not state.area and (not state.city or state.city == area.city.code):
        state.area, state.city = area.code, area.city.code
    if not state.preferred_time_text and fields.get("preferred_time_text"):
        state.preferred_time_text = str(fields["preferred_time_text"])[:120]
    if state.budget_pkr is None and isinstance(fields.get("budget_pkr"), int):
        state.budget_pkr = fields["budget_pkr"]
    # Suggestions never bypass the rules; anything that would not validate is simply not prefilled.
    for name in rules.check(state, complete=False):
        setattr(state, name, rules.State().__dict__[name])
    apply_state(job, state)


# --- Views ----------------------------------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class JobListCreateView(ListAPIView):
    """GET /jobs/?status=draft|confirmed (paginated) · POST /jobs/ → new draft."""

    permission_classes = [IsCustomer]
    throttle_classes = [JobsThrottle]

    def get_queryset(self):
        queryset = own_jobs(self.request).order_by("-updated_at")
        wanted = self.request.query_params.get("status")
        if wanted in JobRequest.Status.values:
            queryset = queryset.filter(status=wanted)
        return queryset

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([list_payload(job) for job in page])

    def post(self, request):
        serializer = CreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        clip = None
        if data["source_kind"] == "voice":
            clip = AudioClip.objects.filter(
                pk=data["audio_clip_id"], owner=request.user, purpose=Purpose.JOB_DESCRIPTION
            ).first()
            if clip is None:
                raise ValidationError({"audio_clip_id": [ErrorDetail("Voice note not found.", code="not_found")]})
        job = JobRequest.objects.create(
            customer=request.user,
            source_kind=data["source_kind"],
            source_language=data["source_language"],
            original_text=data.get("original_text", "") if data["source_kind"] == "text" else "",
            audio_clip=clip,
            description=data.get("original_text", "") if data["source_kind"] == "text" else "",
        )
        logger.info("Job request draft created (source=%s).", job.source_kind)
        return Response(job_payload(own_jobs(request).get(pk=job.pk)), status=status.HTTP_201_CREATED)


@method_decorator(never_cache, name="dispatch")
class JobDetailView(APIView):
    """GET /jobs/{id}/ · PATCH (draft only) · DELETE (draft only)."""

    permission_classes = [IsCustomer]
    throttle_classes = [JobsThrottle]

    def get(self, request, job_id):
        job = own_jobs(request).filter(pk=job_id).first()
        if job is None:
            raise NotFound()
        return Response(job_payload(job))

    def patch(self, request, job_id):
        serializer = DetailsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            job = get_own_job(request, job_id, lock=True)
            if job.status != JobRequest.Status.DRAFT:
                raise NotEditable()
            state = state_of(job)
            for name, value in serializer.validated_data.items():
                setattr(state, name, value)
            if "area" in serializer.validated_data and state.area and "city" not in serializer.validated_data:
                area = Area.objects.filter(code=state.area).select_related("city").first()
                state.city = area.city.code if area else state.city
            for name in ("services", "services_excluded"):
                setattr(state, name, list(dict.fromkeys(getattr(state, name))))
            errors = rules.check(state, complete=False)
            if errors:
                _raise(errors)  # nothing saved: the previous draft stays as it was
            apply_state(job, state)
        return Response(job_payload(own_jobs(request).get(pk=job.pk)))

    def delete(self, request, job_id):
        with transaction.atomic():
            job = get_own_job(request, job_id, lock=True)
            if job.status != JobRequest.Status.DRAFT:
                raise NotEditable()
            for photo in job.photos.all():
                photo.file.delete(save=False)
            job.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(never_cache, name="dispatch")
class JobSourceView(APIView):
    """POST /jobs/{id}/source/ {transcription_id?, interpretation_id?} — attach the customer's OWN voice
    transcript and/or AI interpretation; the original text is set once and suggestions fill empty fields."""

    permission_classes = [IsCustomer]
    throttle_classes = [JobsThrottle]

    def post(self, request, job_id):
        serializer = SourceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            job = get_own_job(request, job_id, lock=True)
            if job.status != JobRequest.Status.DRAFT:
                raise NotEditable()
            if "transcription_id" in data:
                transcription = Transcription.objects.filter(
                    pk=data["transcription_id"], clip__owner=request.user
                ).select_related("clip").first()
                if transcription is None:
                    raise ValidationError({"transcription_id": [ErrorDetail("Not found.", code="not_found")]})
                if job.audio_clip_id and transcription.clip_id != job.audio_clip_id:
                    raise SourceMismatch()
                self._set_original(job, transcription.text, transcription.language)
                job.transcription = transcription
                job.audio_clip = job.audio_clip or transcription.clip
                job.save()
            if "interpretation_id" in data:
                interpretation = Interpretation.objects.filter(
                    pk=data["interpretation_id"], owner=request.user, kind=Purpose.JOB_DESCRIPTION
                ).first()
                if interpretation is None:
                    raise ValidationError({"interpretation_id": [ErrorDetail("Not found.", code="not_found")]})
                if interpretation.transcription_id and job.transcription_id and interpretation.transcription_id != job.transcription_id:
                    raise SourceMismatch()
                self._set_original(job, interpretation.source_text, interpretation.language)
                job.interpretation = interpretation
                job.save()
                prefill_from(job, interpretation)
        return Response(job_payload(own_jobs(request).get(pk=job.pk)))

    @staticmethod
    def _set_original(job: JobRequest, text: str, language: str) -> None:
        if not job.original_text:
            job.original_text = text
            if language in ("ur", "en", "mixed"):
                job.source_language = language
        elif " ".join(job.original_text.split()) != " ".join(text.split()):
            raise SourceMismatch()


@method_decorator(never_cache, name="dispatch")
class JobConfirmView(APIView):
    """POST /jobs/{id}/confirm/ — validate everything and confirm. Idempotent: a confirmed request
    is returned unchanged (still one request). Validation failures leave the draft untouched."""

    permission_classes = [IsCustomer]
    throttle_classes = [JobsThrottle]

    def post(self, request, job_id):
        with transaction.atomic():
            job = get_own_job(request, job_id, lock=True)
            if job.status == JobRequest.Status.CONFIRMED:
                return Response({**job_payload(own_jobs(request).get(pk=job.pk)), "already_confirmed": True})
            errors = rules.check(state_of(job), complete=True)
            if errors:
                _raise(errors)
            job.status = JobRequest.Status.CONFIRMED
            job.confirmed_at = timezone.now()
            job.save(update_fields=["status", "confirmed_at", "updated_at"])
        logger.info("Job request confirmed.")
        return Response({**job_payload(own_jobs(request).get(pk=job.pk)), "already_confirmed": False})


class JobPhotosThrottle(JobsThrottle):
    scope = "job_photo_user"


@method_decorator(never_cache, name="dispatch")
class JobPhotosView(APIView):
    """POST /jobs/{id}/photos/ multipart {image} — draft only, at most five."""

    permission_classes = [IsCustomer]
    parser_classes = [MultiPartParser]
    throttle_classes = [JobPhotosThrottle]

    def post(self, request, job_id):
        if int(request.META.get("CONTENT_LENGTH") or 0) > photo_rules.MAX_BYTES + 64 * 1024:
            raise photo_rules.PhotoTooLarge()
        upload = request.data.get("image")
        if upload is None or not hasattr(upload, "read"):
            raise ValidationError({"image": [ErrorDetail("Add a photo.", code="required")]})
        try:
            if upload.size > photo_rules.MAX_BYTES:
                raise photo_rules.PhotoTooLarge()
            clean = photo_rules.clean_photo(upload.read())
        finally:
            upload.close()
        with transaction.atomic():
            job = get_own_job(request, job_id, lock=True)
            if job.status != JobRequest.Status.DRAFT:
                raise NotEditable()
            if job.photos.count() >= photo_rules.MAX_PHOTOS:
                raise photo_rules.TooManyPhotos()
            photo = JobPhoto(job=job, mime_type=clean.mime_type, size_bytes=len(clean.data), width=clean.width,
                             height=clean.height, sha256=clean.sha256)
            photo.file.save("photo", ContentFile(clean.data), save=False)
            photo.save()
            job.save(update_fields=["updated_at"])
        return Response(photo_payload(photo), status=status.HTTP_201_CREATED)


@method_decorator(never_cache, name="dispatch")
class JobPhotoDetailView(APIView):
    """DELETE /jobs/{id}/photos/{photo_id}/ (draft only)."""

    permission_classes = [IsCustomer]
    throttle_classes = [JobsThrottle]

    def delete(self, request, job_id, photo_id):
        with transaction.atomic():
            job = get_own_job(request, job_id, lock=True)
            if job.status != JobRequest.Status.DRAFT:
                raise NotEditable()
            photo = job.photos.filter(pk=photo_id).first()
            if photo is None:
                raise NotFound()
            photo.file.delete(save=False)
            photo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class JobPhotoContentView(APIView):
    """GET /jobs/{id}/photos/{photo_id}/content/ — the owner only; private, never cached."""

    permission_classes = [IsCustomer]

    def get(self, request, job_id, photo_id):
        photo = JobPhoto.objects.filter(pk=photo_id, job_id=job_id, job__customer=request.user).first()
        if photo is None:
            raise NotFound()
        response = FileResponse(photo.file.open("rb"), content_type=photo.mime_type)
        response["Content-Disposition"] = 'inline; filename="photo"'
        response["Cache-Control"] = "private, no-store"
        return response


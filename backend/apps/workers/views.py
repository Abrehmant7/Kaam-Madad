"""Worker onboarding, dashboard and identity-verification API (M4). Contracts: docs/api.md."""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status
from rest_framework.exceptions import ErrorDetail, NotFound, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsWorker
from apps.accounts.serializers import StrictFieldsMixin
from apps.accounts.throttles import ConfigurableRateThrottle
from apps.catalog.models import Area, City, ServiceTag, Trade
from apps.providers.errors import ProviderError
from apps.voice.views import provider_api_error

from . import identity, onboarding
from .eligibility import worker_eligibility
from .models import IdentityVerification, WorkerProfile

class IdentityThrottle(ConfigurableRateThrottle):
    scope = "identity_user"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


def _codes(manager) -> list[str]:
    return sorted(item.code for item in manager.all())


def get_profile(user) -> WorkerProfile:
    profile, _ = WorkerProfile.objects.get_or_create(user=user)
    return profile


def dashboard_payload(user, profile: WorkerProfile) -> dict:
    return {
        "profile": {
            "trade": profile.trade.code if profile.trade else None,
            "services_offered": _codes(profile.services_offered),
            "primary_specialities": _codes(profile.primary_specialities),
            "services_not_offered": _codes(profile.services_not_offered),
            "city": profile.city.code if profile.city else None,
            "service_areas": _codes(profile.service_areas),
            "accepting_requests": profile.accepting_requests,
            "updated_at": profile.updated_at.isoformat(),
        },
        "onboarding": onboarding.onboarding_state(profile),
        "identity": identity.identity_summary(identity.current_case(user)),
        "eligibility": worker_eligibility(user, profile).as_dict(),
        "identity_provider": identity.provider_status(),
    }


def _raise_field_errors(errors: onboarding.FieldErrors) -> None:
    raise ValidationError(
        {field: [ErrorDetail(message, code=code) for code, message in items] for field, items in errors.errors.items()}
    )


class CodeList(serializers.ListField):
    def __init__(self, **kwargs):
        super().__init__(child=serializers.SlugField(max_length=64), allow_empty=True, max_length=50, **kwargs)


class WorkSerializer(StrictFieldsMixin, serializers.Serializer):
    trade = serializers.SlugField(max_length=64, allow_blank=True)
    services_offered = CodeList()
    primary_specialities = CodeList()
    services_not_offered = CodeList(required=False, default=list)


class AreasSerializer(StrictFieldsMixin, serializers.Serializer):
    city = serializers.SlugField(max_length=64, allow_blank=True)
    service_areas = CodeList()


class PreferencesSerializer(StrictFieldsMixin, serializers.Serializer):
    accepting_requests = serializers.BooleanField()


@method_decorator(never_cache, name="dispatch")
class WorkerMeView(APIView):
    """GET /api/v1/workers/me/ — profile, onboarding progress, identity status, eligibility."""

    permission_classes = [IsWorker]

    def get(self, request):
        return Response(dashboard_payload(request.user, get_profile(request.user)))


@method_decorator(never_cache, name="dispatch")
class WorkStepView(APIView):
    """PUT /api/v1/workers/me/work/ — screen 2: trade, services, main speciality, exclusions."""

    permission_classes = [IsWorker]

    def put(self, request):
        serializer = WorkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        offered = list(dict.fromkeys(data["services_offered"]))
        primary = list(dict.fromkeys(data["primary_specialities"]))
        excluded = list(dict.fromkeys(data["services_not_offered"]))
        errors = onboarding.validate_work(data["trade"], offered, primary, excluded)
        if errors:
            _raise_field_errors(errors)
        with transaction.atomic():
            profile = get_profile(request.user)
            profile.trade = Trade.objects.get(code=data["trade"])
            profile.work_saved_at = timezone.now()
            profile.save()
            profile.services_offered.set(ServiceTag.objects.filter(code__in=offered))
            profile.primary_specialities.set(ServiceTag.objects.filter(code__in=primary))
            profile.services_not_offered.set(ServiceTag.objects.filter(code__in=excluded))
        return Response(dashboard_payload(request.user, profile))


@method_decorator(never_cache, name="dispatch")
class AreasStepView(APIView):
    """PUT /api/v1/workers/me/areas/ — screen 3: city and the areas the worker will travel to."""

    permission_classes = [IsWorker]

    def put(self, request):
        serializer = AreasSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        areas = list(dict.fromkeys(data["service_areas"]))
        errors = onboarding.validate_areas(data["city"], areas)
        if errors:
            _raise_field_errors(errors)
        with transaction.atomic():
            profile = get_profile(request.user)
            profile.city = City.objects.get(code=data["city"])
            profile.areas_saved_at = timezone.now()
            profile.save()
            profile.service_areas.set(Area.objects.filter(code__in=areas))
        return Response(dashboard_payload(request.user, profile))


@method_decorator(never_cache, name="dispatch")
class PreferencesView(APIView):
    """PATCH /api/v1/workers/me/preferences/ {accepting_requests} — separate from completion/identity."""

    permission_classes = [IsWorker]

    def patch(self, request):
        serializer = PreferencesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = get_profile(request.user)
        profile.accepting_requests = serializer.validated_data["accepting_requests"]
        profile.save(update_fields=["accepting_requests", "updated_at"])
        return Response(dashboard_payload(request.user, profile))


# --- Identity verification ---------------------------------------------------------------------


class StartSerializer(StrictFieldsMixin, serializers.Serializer):
    consent = serializers.BooleanField()

    def validate_consent(self, value):
        if value is not True:
            raise serializers.ValidationError("Consent is required to continue.", code="consent_required")
        return value


class SubmitSerializer(StrictFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=80, trim_whitespace=True)
    cnic_number = serializers.CharField(max_length=20, trim_whitespace=True)

    def validate_name(self, value):
        cleaned = identity.clean_name(value)
        if len(cleaned) < 2 or any(ch.isdigit() for ch in cleaned):
            raise serializers.ValidationError("Enter the name as printed on the card.", code="invalid_name")
        return cleaned

    def validate_cnic_number(self, value):
        digits = identity.normalize_cnic(value)
        if digits is None:
            raise serializers.ValidationError("Enter the 13-digit CNIC number.", code="invalid_cnic")
        return digits


def _own_case(request, case_id) -> IdentityVerification:
    case = IdentityVerification.objects.filter(pk=case_id, user=request.user).first()
    if case is None or case.status == IdentityVerification.Status.SUPERSEDED:
        raise NotFound()
    return case


@method_decorator(never_cache, name="dispatch")
class IdentityCasesView(APIView):
    """GET current attempt (or null) / POST {consent: true} to start a new attempt."""

    permission_classes = [IsWorker]
    throttle_classes = [IdentityThrottle]

    def get(self, request):
        case = identity.current_case(request.user)
        return Response({"case": identity.case_payload(case) if case else None, "provider": identity.provider_status()})

    def post(self, request):
        StartSerializer(data=request.data).is_valid(raise_exception=True)
        case = identity.start_case(request.user)
        return Response({"case": identity.case_payload(case), "provider": identity.provider_status()}, status=201)


@method_decorator(never_cache, name="dispatch")
class IdentityScanView(APIView):
    """POST multipart {image} — photo of the card front → OCR draft (name, number). Image not stored."""

    permission_classes = [IsWorker]
    parser_classes = [MultiPartParser]
    throttle_classes = [IdentityThrottle]

    def post(self, request, case_id):
        case = _own_case(request, case_id)
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
        if declared > settings.IDENTITY_LIMITS["MAX_IMAGE_BYTES"] + 64 * 1024:
            raise identity.ImageTooLarge()
        upload = request.data.get("image")
        if upload is None or not hasattr(upload, "read"):
            raise ValidationError({"image": [ErrorDetail("Add a photo of the card.", code="required")]})
        try:
            if upload.size > settings.IDENTITY_LIMITS["MAX_IMAGE_BYTES"]:
                raise identity.ImageTooLarge()
            identity.scan_card(case, upload.read())
        except ProviderError as exc:
            error = provider_api_error(exc, "cnic_ocr")
            error.details = {**(error.details or {}), "case": identity.case_payload(case)}
            raise error from None
        finally:
            upload.close()  # Django deletes any temporary upload file when it is closed
        return Response({"case": identity.case_payload(case)})


@method_decorator(never_cache, name="dispatch")
class IdentitySubmitView(APIView):
    """POST {name, cnic_number} — details the worker confirmed or corrected → registry check."""

    permission_classes = [IsWorker]
    throttle_classes = [IdentityThrottle]

    def post(self, request, case_id):
        case = _own_case(request, case_id)
        serializer = SubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identity.submit_details(case, serializer.validated_data["name"], serializer.validated_data["cnic_number"])
        profile = get_profile(request.user)
        return Response({
            "case": identity.case_payload(case),
            "eligibility": worker_eligibility(request.user, profile).as_dict(),
        })

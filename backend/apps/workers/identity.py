"""Identity verification service (ID-01, ID-02, ID-04).

Separate steps, each reported on its own:
1. Scan — ``scan_card`` validates the uploaded photo (type, size, dimensions), runs the real OCR
   provider (Tesseract on this host) and keeps only the extracted NAME and NUMBER as a draft for
   the owner. The image is not stored; OCR's temporary files are deleted. OCR never approves.
2. Review — the worker confirms or corrects both fields (corrections are recorded as such).
3. Registry — ``submit_details`` checks the number format in code and asks the identity provider.
   In a demo deployment that is the fictional ``DemoIdentityRecord`` registry: the name AND the
   number must match the SAME record (case/spacing differences in the name are ignored; a known
   number with a different name fails). Otherwise the unconfigured boundary is used (authorised
   NADRA access does not exist yet), which never approves.

CNIC numbers are kept as a keyed digest (``salted_hmac``) plus a masked form; they and the raw
OCR text are never logged and never sent to the speech pipeline.
"""

from __future__ import annotations

import io
import logging
import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework import status

from apps.core.api.exceptions import ApiError
from apps.providers import registry as provider_registry
from apps.providers.errors import ProviderError, ProviderNotConfigured
from apps.providers.identity import (
    IdentityVerificationProvider,
    IdentityVerificationResult,
    UnconfiguredIdentityVerification,
)
from config.env import DEPLOYMENT_MODE_DEMO

from .models import DemoIdentityRecord, IdentityVerification

logger = logging.getLogger(__name__)

_SEPARATORS = re.compile(r"[\s\-]")
_CNIC = re.compile(r"^\d{13}$")
IMAGE_TYPES = {
    "image/jpeg": lambda b: b[:3] == b"\xff\xd8\xff",
    "image/png": lambda b: b[:8] == b"\x89PNG\r\n\x1a\n",
    "image/webp": lambda b: len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP",
}
PIL_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


# --- Errors ------------------------------------------------------------------------------


class ImageTooLarge(ApiError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_code = "image_too_large"
    default_detail = "The photo is too large. Please use a photo under 5 MB."


class ImageUnsupported(ApiError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_code = "image_unsupported"
    default_detail = "Please use a JPEG, PNG or WebP photo of the card."


class ImageDimensions(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "image_dimensions"
    default_detail = "The photo is too small or too large to read. Take a closer, clear photo of the card."


class VerificationLocked(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "verification_not_editable"
    default_detail = "This verification attempt can no longer be changed."


class AlreadyVerified(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "verification_already_complete"
    default_detail = "Your identity check is already complete."


class ScanRequired(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "verification_scan_required"
    default_detail = "Scan the front of the card first."


class IdentityProviderUnavailable(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "identity_provider_not_configured"
    default_detail = "Identity checks are not available on this server yet."


# --- Helpers ---------------------------------------------------------------------------------


def normalize_cnic(value: str) -> str | None:
    """13 digits, with or without dashes/spaces (12345-1234567-1). Format only — not authenticity."""
    if not isinstance(value, str):
        return None
    digits = _SEPARATORS.sub("", value.strip())
    return digits if _CNIC.match(digits) else None


def normalize_name(value: str) -> str:
    """Comparison form: case and spacing differences are harmless."""
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def cnic_digest(digits: str) -> str:
    return salted_hmac("kaam-madad.identity.cnic", digits, algorithm="sha256").hexdigest()


def mask_cnic(digits: str) -> str:
    """Show only the last three digits: *****-*****67-8."""
    return f"*****-*****{digits[10:12]}-{digits[12]}"


def format_cnic(digits: str) -> str:
    return f"{digits[:5]}-{digits[5:12]}-{digits[12]}"


def demo_mode() -> bool:
    return settings.DEPLOYMENT_MODE == DEPLOYMENT_MODE_DEMO


# --- Registry provider --------------------------------------------------------------------------


class DemoRegistryVerification(IdentityVerificationProvider):
    """Name AND number must match the same FICTIONAL record. Demo deployments only."""

    name = "demo_registry"
    simulated = True

    def verify(self, *, confirmed_fields: dict[str, str], consent_reference: str) -> IdentityVerificationResult:
        record = DemoIdentityRecord.objects.filter(
            cnic_digest=cnic_digest(confirmed_fields["cnic_number"]), is_active=True
        ).first()
        if record is None:
            outcome, reference, extra = "no_record", "", {}
        elif normalize_name(record.full_name_en) != normalize_name(confirmed_fields["name"]):
            outcome, reference, extra = "name_mismatch", "", {}  # never reveal the recorded name
        else:
            outcome, reference, extra = "verified", record.reference, {"demo_address": record.demo_address}
        return IdentityVerificationResult(
            outcome=outcome, provider_reference=reference, method="demo_registry", provider=self.name,
            simulated=True, extra=extra,
        )


def verification_provider() -> IdentityVerificationProvider:
    # The demo registry is refused at startup in live mode and, as defence in depth, here too.
    if settings.IDENTITY_VERIFICATION_PROVIDER == "demo_registry" and demo_mode():
        return DemoRegistryVerification()
    return UnconfiguredIdentityVerification()


def provider_status() -> dict:
    provider = verification_provider()
    return {"provider": provider.name, "available": provider.name != "unconfigured", "simulated": provider.simulated}


# --- Case operations ----------------------------------------------------------------------------


def current_case(user) -> IdentityVerification | None:
    return IdentityVerification.objects.filter(user=user).exclude(status=IdentityVerification.Status.SUPERSEDED).first()


def start_case(user) -> IdentityVerification:
    with transaction.atomic():
        existing = current_case(user)
        if existing and existing.status == IdentityVerification.Status.SUSPENDED:
            raise VerificationLocked()  # a staff suspension is not bypassed by starting over
        if existing and existing.status in (
            IdentityVerification.Status.PROVIDER_VERIFIED, IdentityVerification.Status.MANUALLY_REVIEWED,
        ):
            raise AlreadyVerified()
        if existing and existing.status == IdentityVerification.Status.DEMO_APPROVED and demo_mode():
            raise AlreadyVerified()
        if existing:
            existing.status = IdentityVerification.Status.SUPERSEDED
            existing.ocr_name_pending = existing.ocr_number_pending = ""
            existing.save(update_fields=["status", "ocr_name_pending", "ocr_number_pending", "updated_at"])
        return IdentityVerification.objects.create(
            user=user, consent_given_at=timezone.now(), consent_version=IdentityVerification.CONSENT_VERSION,
        )


def _ensure_editable(case: IdentityVerification) -> None:
    if case.status not in IdentityVerification.ACTIVE_STATUSES:
        raise VerificationLocked()


def inspect_image(data: bytes) -> tuple[str, int, int]:
    """Type by content, size, decodability and dimensions — before any OCR runs."""
    from PIL import Image, UnidentifiedImageError

    limits = settings.IDENTITY_LIMITS
    if len(data) > limits["MAX_IMAGE_BYTES"]:
        raise ImageTooLarge(details={"max_bytes": limits["MAX_IMAGE_BYTES"]})
    mime_type = next(
        (kind for kind, matches in IMAGE_TYPES.items() if len(data) >= limits["MIN_IMAGE_BYTES"] and matches(data)), None
    )
    if mime_type is None:
        raise ImageUnsupported()
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != PIL_FORMATS[mime_type]:
                raise ImageUnsupported()
            width, height = image.size
            if width * height > limits["MAX_PIXELS"]:
                raise ImageDimensions(details={"reason": "too_large"})
            image.verify()  # structural check without decoding all pixels
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ImageUnsupported() from None
    short, long = sorted((width, height))
    if short < min(limits["MIN_WIDTH"], limits["MIN_HEIGHT"]) or long < max(limits["MIN_WIDTH"], limits["MIN_HEIGHT"]):
        raise ImageDimensions(details={"reason": "too_small", "min_width": limits["MIN_WIDTH"],
                                       "min_height": limits["MIN_HEIGHT"]})
    return mime_type, width, height


def scan_card(case: IdentityVerification, data: bytes) -> None:
    """Validate the photo and run OCR on it. Provider errors are recorded and re-raised for the API."""
    _ensure_editable(case)
    mime_type, width, height = inspect_image(data)
    now = timezone.now()
    case.scan_count += 1
    case.scanned_at = now
    case.scan_mime_type, case.scan_width, case.scan_height, case.scan_size_bytes = mime_type, width, height, len(data)
    case.ocr_name_pending = case.ocr_number_pending = ""
    try:
        provider = provider_registry.cnic_ocr()
        result = provider.extract(image=data, mime_type=mime_type)
    except ProviderError as exc:
        case.ocr_status = IdentityVerification.OcrStatus.FAILED
        case.ocr_failure_reason = f"{exc.code}:{exc.reason}"[:64]
        case.save()
        logger.warning("CNIC scan failed (%s, %s).", exc.code, exc.reason)
        raise
    case.ocr_status = result.status
    case.ocr_provider = result.provider
    case.ocr_engine = result.engine
    case.ocr_rotation = result.rotation
    case.ocr_failure_reason = ""
    case.ocr_name_pending = (result.name or "")[:80]
    case.ocr_number_pending = result.cnic_number or ""
    case.save()
    logger.info("CNIC scan processed (status=%s, rotation=%s).", result.status, result.rotation)


def submit_details(case: IdentityVerification, name: str, digits: str) -> dict:
    """Registry step for details the worker confirmed. Returns non-secret extras (e.g. demo address)."""
    _ensure_editable(case)
    if case.ocr_status not in IdentityVerification.SCANNED_STATUSES:
        raise ScanRequired()  # details must follow a processed scan of the card
    provider = verification_provider()
    now = timezone.now()
    name = clean_name(name)
    # Corrections stay distinguishable from the scan (compared with the ORIGINAL OCR draft, which is
    # kept for retries while the attempt is open and cleared once it is approved).
    case.name_corrected = normalize_name(name) != normalize_name(case.ocr_name_pending)
    case.number_corrected = digits != case.ocr_number_pending
    case.cnic_digest = cnic_digest(digits)
    case.cnic_masked = mask_cnic(digits)
    case.submitted_at = now
    case.submission_count += 1
    try:
        result = provider.verify(confirmed_fields={"cnic_number": digits, "name": name}, consent_reference=str(case.id))
    except ProviderNotConfigured:
        case.save()
        raise IdentityProviderUnavailable() from None
    case.registry_provider = result.provider
    case.registry_simulated = result.simulated
    case.registry_checked_at = now
    if result.outcome == "verified":
        case.registry_outcome = IdentityVerification.RegistryOutcome.MATCH
        case.registry_reference = result.provider_reference
        case.method = result.method
        case.status = (
            IdentityVerification.Status.DEMO_APPROVED if result.simulated else IdentityVerification.Status.PROVIDER_VERIFIED
        )
        case.decided_at = now
        case.ocr_name_pending = case.ocr_number_pending = ""  # nothing in clear text remains
    else:
        case.registry_outcome = (
            IdentityVerification.RegistryOutcome.NAME_MISMATCH
            if result.outcome == "name_mismatch" else IdentityVerification.RegistryOutcome.NO_RECORD
        )
        case.registry_reference = ""
        case.status = IdentityVerification.Status.NO_MATCH
    case.save()
    logger.info("Identity check recorded (provider=%s, outcome=%s).", result.provider, result.outcome)
    return result.extra


class DemoVerificationUnavailable(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "demo_verification_unavailable"
    default_detail = "Demo verification is only available in a demo deployment."


DEMO_SAMPLE_CONSENT_VERSION = "demo-sample-v1"  # max 16 characters


def demo_sample_verify(user, cnic_image: bytes, selfie_image: bytes) -> IdentityVerification:
    """Event demo flow: a sample CNIC and a sample selfie, each validated with the normal image limits, then the
    existing ``demo_approved`` status. Nothing else is checked: no OCR, name/number extraction, face matching or
    registry lookup. The images are never stored and never sent to a provider; only image metadata is kept.

    Refused outside a demo deployment (the approval would not count there anyway: see ``eligibility``).
    """
    if not demo_mode():
        raise DemoVerificationUnavailable()
    card_type, card_width, card_height = inspect_image(cnic_image)
    inspect_image(selfie_image)
    now = timezone.now()
    with transaction.atomic():
        case = start_case(user)  # same rules: suspended → locked; already approved → 409; earlier attempt superseded
        case.consent_given_at, case.consent_version = now, DEMO_SAMPLE_CONSENT_VERSION
        case.scan_count, case.scanned_at = 1, now
        case.scan_mime_type, case.scan_width, case.scan_height, case.scan_size_bytes = (
            card_type, card_width, card_height, len(cnic_image),
        )
        case.method = IdentityVerification.Method.DEMO_SAMPLE_UPLOAD
        case.status = IdentityVerification.Status.DEMO_APPROVED
        case.registry_provider, case.registry_simulated = "demo_sample_upload", True
        case.decided_at = now
        case.save()
    logger.info("Demo verification with sample images recorded (no identity check).")
    return case


# --- Payloads -----------------------------------------------------------------------------------


def identity_summary(case: IdentityVerification | None) -> dict:
    """Status for the worker's own dashboard: masked number only, no image, no digest."""
    if case is None:
        return {"status": "not_started", "case_id": None, "method": None, "masked_cnic": None,
                "simulated": False, "counts_here": False, "decided_at": None, "updated_at": None}
    counts = case.status in (IdentityVerification.Status.PROVIDER_VERIFIED, IdentityVerification.Status.MANUALLY_REVIEWED) or (
        case.status == IdentityVerification.Status.DEMO_APPROVED and demo_mode()
    )
    return {
        "status": case.status,
        "case_id": str(case.id),
        "method": case.method or None,
        "masked_cnic": case.cnic_masked or None,
        "simulated": case.registry_simulated or case.status == IdentityVerification.Status.DEMO_APPROVED,
        "counts_here": counts,
        "decided_at": case.decided_at.isoformat() if case.decided_at else None,
        "updated_at": case.updated_at.isoformat(),
    }


def demo_address_for(case: IdentityVerification) -> str | None:
    if case.registry_outcome != IdentityVerification.RegistryOutcome.MATCH or not case.registry_simulated:
        return None
    record = DemoIdentityRecord.objects.filter(reference=case.registry_reference).first()
    return (record.demo_address or None) if record else None


def case_payload(case: IdentityVerification) -> dict:
    """Owner-only view of one attempt, with scan, review and registry steps reported separately."""
    return {
        "id": str(case.id),
        **identity_summary(case),
        "consent": {"given_at": case.consent_given_at.isoformat(), "version": case.consent_version},
        "scan": {
            "count": case.scan_count,
            "scanned_at": case.scanned_at.isoformat() if case.scanned_at else None,
            "width": case.scan_width,
            "height": case.scan_height,
        },
        "ocr": {
            "status": case.ocr_status or "not_run",
            "provider": case.ocr_provider or None,
            "engine": case.ocr_engine or None,
            "rotation": case.ocr_rotation,
            "failure": case.ocr_failure_reason.split(":")[1] if ":" in case.ocr_failure_reason else None,
            "simulated": False,
            # The ORIGINAL scan result for the owner's review; cleared once the attempt is approved.
            "name": case.ocr_name_pending or None,
            "cnic_number": format_cnic(case.ocr_number_pending) if case.ocr_number_pending else None,
        },
        "review": {
            "submitted_at": case.submitted_at.isoformat() if case.submitted_at else None,
            "name_corrected": case.name_corrected,
            "number_corrected": case.number_corrected,
        },
        "registry": {
            "outcome": case.registry_outcome or "not_checked",
            "provider": case.registry_provider or None,
            "simulated": case.registry_simulated,
            "reference": case.registry_reference or None,
            "checked_at": case.registry_checked_at.isoformat() if case.registry_checked_at else None,
            "attempts": case.submission_count,
            # Fictional, shown labelled "Demo address"; never used as a service area.
            "demo_address": demo_address_for(case),
        },
    }

"""Shareable view of a confirmed request for M6 matching and invitations.

M6 must build recommendations and invitation previews from ``matching_summary(job)`` only. It
leaves out everything private to the customer: the exact address, access notes, photos, the
original audio/transcript and the customer's identity. The customer's budget preference is
included as such (never as a quote).
"""

from __future__ import annotations

import re
from datetime import UTC

from .models import JobRequest

# Eastern Arabic / Urdu digits → ASCII, so "۰۳۰۰…" is recognised too.
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_PHONE = re.compile(r"(?:\+?92|0)[\s-]*3\d{2}[\s-]*\d{3}[\s-]*\d{4}|\d[\d\s-]{9,}\d")
_ADDRESS_WORDS = re.compile(
    r"(?<![A-Za-z])(?:house|street|flat|plot|apartment|lane|block|st\.|h\.?\s?no)(?![A-Za-z])"
    r"|مکان|گلی|فلیٹ|پلاٹ|بلاک|گھر نمبر|اسٹریٹ|سٹریٹ",
    re.IGNORECASE,
)


def privacy_warnings(text: str) -> list[str]:
    """Hints for the customer before sharing free text: ``phone_number`` and/or ``address``.

    The structured address field is never shared, but text the customer typed into the
    description is shared as written, so it is checked here (a reminder, not a guarantee).
    """
    normalised = (text or "").translate(_DIGITS)
    warnings = []
    if _PHONE.search(normalised):
        warnings.append("phone_number")
    if _ADDRESS_WORDS.search(normalised):
        warnings.append("address")
    return warnings


def _utc(value) -> str:
    """Always the same text for the same instant: UTC with a trailing Z."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def matching_summary(job: JobRequest) -> dict:
    if job.status != JobRequest.Status.CONFIRMED:
        raise ValueError("Only confirmed requests can be matched.")
    return {
        "id": str(job.id),
        "description": job.description,
        "trade": job.trade.code,
        "services": sorted(s.code for s in job.services.all()),
        "services_excluded": sorted(s.code for s in job.services_excluded.all()),
        "city": job.city.code,
        "area": job.area.code,
        "window_start": _utc(job.window_start),
        "window_end": _utc(job.window_end),
        "budget_preference_pkr": str(job.budget_pkr) if job.budget_pkr is not None else None,
        "has_photos": job.photos.exists(),
    }

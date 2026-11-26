"""Shareable view of a confirmed request for M6 matching and invitations.

M6 must build recommendations and invitation previews from ``matching_summary(job)`` only. It
leaves out everything private to the customer: the exact address, access notes, photos, the
original audio/transcript and the customer's identity. The customer's budget preference is
included as such (never as a quote).
"""

from __future__ import annotations

from .models import JobRequest


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
        "window_start": job.window_start.isoformat(),
        "window_end": job.window_end.isoformat(),
        "budget_preference_pkr": str(job.budget_pkr) if job.budget_pkr is not None else None,
        "has_photos": job.photos.exists(),
    }

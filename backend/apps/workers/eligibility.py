"""Shared marketplace eligibility check for workers (ID-04, WK-05).

    from apps.workers.eligibility import worker_eligibility
    result = worker_eligibility(user)
    if not result.can_take_jobs: ...          # result.reasons explains why

Callers that MUST use it (M4 only defines it):
- M6 recommendations: only list workers where ``worker_eligibility(user).receives_requests``
  (eligible AND the worker's own accepting-requests preference is on), and re-check before
  sending an invitation.
- M8 booking finalisation: call ``worker_eligibility(user).can_take_jobs`` inside the booking
  transaction (after locking the worker row) and refuse to confirm when it is False.
  A paused worker (accepting_requests off) can still finish existing bookings.

Rules:
- worker account, active (``is_active``);
- complete profile, re-validated against the live catalog (``onboarding.is_complete``);
- identity status acceptable *for this deployment*: provider_verified or manually_reviewed
  anywhere; demo_approved ONLY in a demo deployment (ID-04 — no mixed live/demo directory).
Phone confirmation is not an identity check and is not part of eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .identity import current_case, demo_mode
from .models import IdentityVerification, WorkerProfile
from .onboarding import is_complete


@dataclass(frozen=True)
class Eligibility:
    can_take_jobs: bool
    receives_requests: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"can_take_jobs": self.can_take_jobs, "receives_requests": self.receives_requests, "reasons": self.reasons}


ACCEPTED_EVERYWHERE = {IdentityVerification.Status.PROVIDER_VERIFIED, IdentityVerification.Status.MANUALLY_REVIEWED}


def identity_reason(case: IdentityVerification | None) -> str | None:
    if case is None:
        return "identity_not_started"
    if case.status in ACCEPTED_EVERYWHERE:
        return None
    if case.status == IdentityVerification.Status.DEMO_APPROVED:
        return None if demo_mode() else "demo_approval_not_accepted_here"
    if case.status in (IdentityVerification.Status.REJECTED, IdentityVerification.Status.EXPIRED,
                       IdentityVerification.Status.SUSPENDED):
        return f"identity_{case.status}"
    if case.status == IdentityVerification.Status.NO_MATCH:
        return "identity_no_match"
    return "identity_not_verified"


def worker_eligibility(user, profile: WorkerProfile | None = None) -> Eligibility:
    reasons: list[str] = []
    if not user.is_worker:
        return Eligibility(False, False, ["not_a_worker"])
    if not user.is_active:
        reasons.append("account_inactive")
    if getattr(user, "restricted_at", None) is not None:  # M10: staff restriction
        reasons.append("account_restricted")
    if profile is None:
        profile = WorkerProfile.objects.filter(user=user).first()
    if profile is None or not is_complete(profile):
        reasons.append("profile_incomplete")
    reason = identity_reason(current_case(user))
    if reason:
        reasons.append(reason)
    can_take = not reasons
    accepting = bool(profile and profile.accepting_requests)
    if can_take and not accepting:
        return Eligibility(True, False, ["not_accepting_requests"])
    return Eligibility(can_take, can_take and accepting, reasons)

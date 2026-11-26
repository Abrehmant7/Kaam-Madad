"""Worker recommendations for a confirmed request (M6: REC-01 to REC-03).

Input is the shareable ``matching_summary(job)`` (customer-confirmed trade, services, area and
window). No AI call is made here: M5 already turned the customer's words into catalog choices.

A worker is a MATCH only if ALL of these hold (``match_profile``):
1. active worker account;
2. profile trade == requested trade;
3. the requested area is one of the worker's service areas (travel coverage, not location);
4. the worker offers EVERY requested service, and lists none of them as "not offered";
5. ``worker_eligibility(user, profile).receives_requests`` — complete profile against the live
   catalog, identity status accepted in THIS deployment (demo approval only in demo mode), and the
   worker's own "accepting requests" choice.

Ranking (``recommend``): more requested services among the worker's main specialities first;
ties broken by the worker profile's opaque UUID (stable across calls, unrelated to sign-up order,
so new workers are not pushed down). Reviews and completed-job history arrive in M9.

Every reason shown to the customer is a stored fact (declared services/specialities, declared
service area, identity status). Services and specialities are the worker's own declarations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.accounts.models import User
from apps.workers.eligibility import worker_eligibility
from apps.workers.identity import current_case
from apps.workers.models import IdentityVerification, WorkerProfile

MAX_RESULTS = 20


@dataclass
class Match:
    profile: WorkerProfile
    services_matched: list[str]
    specialities_matched: list[str]
    verification_status: str
    reasons: list[dict] = field(default_factory=list)

    @property
    def rank_key(self) -> tuple[int, str]:
        return (-len(self.specialities_matched), str(self.profile.id))


def candidate_profiles(summary: dict):
    """Cheap database pre-filter (trade, area, active worker account); full checks in ``match_profile``."""
    return (
        WorkerProfile.objects.filter(
            trade__code=summary["trade"],
            service_areas__code=summary["area"],
            user__is_active=True,
            user__role=User.Role.WORKER,
        )
        .select_related("user", "trade")
        .prefetch_related("services_offered", "primary_specialities", "services_not_offered", "service_areas")
        .distinct()
    )


def match_profile(profile: WorkerProfile, summary: dict) -> Match | None:
    user = profile.user
    if not user.is_active or user.role != User.Role.WORKER:
        return None
    if not profile.trade or profile.trade.code != summary["trade"]:
        return None
    if summary["area"] not in {area.code for area in profile.service_areas.all()}:
        return None
    required = set(summary["services"])
    offered = {s.code for s in profile.services_offered.all()}
    excluded = {s.code for s in profile.services_not_offered.all()}
    if not required or not required <= offered or required & excluded:
        return None
    if not worker_eligibility(user, profile).receives_requests:
        return None

    primary = {s.code for s in profile.primary_specialities.all()}
    specialities = sorted(required & primary)
    others = sorted(required - primary)
    case = current_case(user)
    reasons: list[dict] = []
    if specialities:
        reasons.append({"code": "speciality", "services": specialities})
    if others:
        reasons.append({"code": "offers", "services": others})
    reasons.append({"code": "serves_area", "area": summary["area"]})
    return Match(
        profile=profile,
        services_matched=sorted(required),
        specialities_matched=specialities,
        verification_status=case.status if case else "not_started",
        reasons=reasons,
    )


def recommend(summary: dict) -> list[Match]:
    matches = [m for m in (match_profile(p, summary) for p in candidate_profiles(summary)) if m is not None]
    matches.sort(key=lambda m: m.rank_key)
    return matches[:MAX_RESULTS]


def worker_card(match: Match, previous_status: str | None = None) -> dict:
    """Minimal public card: opaque ID, no name/phone/CNIC/registry data/addresses."""
    status = match.verification_status
    return {
        "worker_id": str(match.profile.id),
        # No approved public display name exists yet; the UI shows the trade plus a short reference.
        "display_label": None,
        "trade": match.profile.trade.code,
        "services_matched": match.services_matched,
        "specialities_matched": match.specialities_matched,
        "serves_selected_area": True,
        "verification": {
            "status": status,
            "simulated": status == IdentityVerification.Status.DEMO_APPROVED,
        },
        # No completed jobs or reviews are recorded before M9: every worker is shown as new.
        "is_new": True,
        "reasons": match.reasons,
        "previous_invitation": previous_status,
    }

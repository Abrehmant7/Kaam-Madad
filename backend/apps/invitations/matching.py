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

Ranking (``recommend``), in order:
1. more requested services among the worker's main specialities (relevance stays first);
2. more customer-confirmed completed jobs that included a requested service (M9 work history);
3. a smoothed visible rating — pulled towards a neutral 3.0 as if there were two extra 3-star reviews, so an
   unrated worker ranks as neutral (not zero) and one 5-star review does not outrank a long record;
4. more visible reviews;
5. the worker profile's opaque UUID (stable tie-breaker, unrelated to sign-up order).
History and ratings come from ``apps.reviews.services.worker_stats`` (two grouped queries for the whole list,
computed from completed bookings and visible reviews — never from editable profile numbers).

Every reason shown to the customer is a stored fact (declared services/specialities, declared
service area, identity status). Services and specialities are the worker's own declarations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from decimal import Decimal

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
    stats: object = None  # apps.reviews.services.WorkerStats

    @property
    def rank_key(self) -> tuple:
        stats = self.stats
        relevant = stats.relevant_jobs if stats else 0
        rating = stats.ranking_rating if stats else Decimal("3")
        count = stats.review_count if stats else 0
        return (-len(self.specialities_matched), -relevant, -rating, -count, str(self.profile.id))


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
    from apps.reviews.services import worker_stats  # reviews depends on bookings, which depends on invitations

    matches = [m for m in (match_profile(p, summary) for p in candidate_profiles(summary)) if m is not None]
    stats = worker_stats([m.profile.id for m in matches], summary["services"])
    for match in matches:
        match.stats = stats.get(str(match.profile.id))
        if match.stats and match.stats.relevant_jobs:
            match.reasons.append({"code": "completed_jobs", "count": match.stats.relevant_jobs, "services": match.services_matched})
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
        # "New worker": no customer-confirmed completed job yet. Ratings come only from visible reviews; an unrated
        # worker has no rating (null), never zero.
        "is_new": not (match.stats and match.stats.completed_jobs),
        "history": match.stats.as_dict() if match.stats else {"completed_jobs": 0, "relevant_jobs": 0, "review_count": 0,
                                                               "average_rating": None},
        "reasons": match.reasons,
        "previous_invitation": previous_status,
    }

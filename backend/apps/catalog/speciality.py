"""Rules shared by the three speciality questions (WK-02).

The questions themselves are database content (SpecialityQuestion). These codes
and rules connect them; M4 onboarding will validate answers with
``validate_speciality_answers`` (also exposed to clients as ``rules``).
"""

from __future__ import annotations

SERVICES_OFFERED = "services_offered"
PRIMARY_SPECIALITIES = "primary_specialities"
SERVICES_NOT_OFFERED = "services_not_offered"

RULES = [
    {
        "type": "disjoint",
        "questions": [SERVICES_OFFERED, SERVICES_NOT_OFFERED],
        "message_code": "offered_and_excluded_overlap",
    },
    {
        "type": "subset",
        "question": PRIMARY_SPECIALITIES,
        "of": SERVICES_OFFERED,
        "message_code": "primary_not_offered",
    },
]


def validate_speciality_answers(answers: dict[str, set[str]], allowed_codes: set[str]) -> list[dict]:
    """Return a list of conflicts; empty means the answers are consistent.

    ``answers`` maps question code → selected service-tag codes.
    """
    offered = set(answers.get(SERVICES_OFFERED, set()))
    primary = set(answers.get(PRIMARY_SPECIALITIES, set()))
    excluded = set(answers.get(SERVICES_NOT_OFFERED, set()))
    conflicts: list[dict] = []

    unknown = (offered | primary | excluded) - allowed_codes
    if unknown:
        conflicts.append({"code": "unknown_service", "services": sorted(unknown)})
    overlap = offered & excluded
    if overlap:
        conflicts.append({"code": "offered_and_excluded_overlap", "services": sorted(overlap)})
    not_offered_primary = primary - offered
    if not_offered_primary:
        conflicts.append({"code": "primary_not_offered", "services": sorted(not_offered_primary)})
    return conflicts

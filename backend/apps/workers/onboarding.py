"""Worker onboarding rules (WK-02, WK-04 as amended, WK-05). The server decides completion.

Steps after account creation (screen 1):
- "work":  trade + services offered + main specialities (+ optional services not offered).
  Validated with the catalog's shared rule set (``apps.catalog.speciality``) and the
  selection limits stored on the SpecialityQuestion rows.
- "areas": a city + one or more active service areas inside that city.

``validate_work`` / ``validate_areas`` check a submission; ``work_issues`` / ``area_issues``
re-check what is stored, so a profile becomes incomplete again if the catalog changes
(e.g. a selected service is deactivated). Nothing is cached as a completion flag.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.catalog import speciality
from apps.catalog.models import Area, City, ServiceTag, SpecialityQuestion, Trade

from .models import WorkerProfile

STEPS = ("work", "areas")
# Default limits if the question rows are missing (they are seeded by seed_catalog).
DEFAULT_LIMITS = {
    speciality.SERVICES_OFFERED: (1, None),
    speciality.PRIMARY_SPECIALITIES: (1, 1),  # exactly one main speciality (M4)
    speciality.SERVICES_NOT_OFFERED: (0, None),
}


@dataclass
class FieldErrors:
    errors: dict[str, list[tuple[str, str]]]

    def add(self, field: str, code: str, message: str) -> None:
        self.errors.setdefault(field, []).append((code, message))

    def __bool__(self) -> bool:
        return bool(self.errors)


def selection_limits() -> dict[str, tuple[int, int | None]]:
    limits = dict(DEFAULT_LIMITS)
    for question in SpecialityQuestion.objects.filter(is_active=True, code__in=list(DEFAULT_LIMITS)):
        limits[question.code] = (question.min_selections, question.max_selections)
    return limits


def validate_work(trade_code: str | None, offered: list[str], primary: list[str], excluded: list[str]) -> FieldErrors:
    errors = FieldErrors({})
    trade = Trade.objects.filter(code=trade_code, is_active=True).first() if trade_code else None
    if trade_code is None or trade_code == "":
        errors.add("trade", "required", "Choose your trade.")
        return errors
    if trade is None:
        errors.add("trade", "unknown_trade", "This trade is not available.")
        return errors

    allowed = set(ServiceTag.objects.filter(trade=trade, is_active=True).values_list("code", flat=True))
    answers = {
        speciality.SERVICES_OFFERED: set(offered),
        speciality.PRIMARY_SPECIALITIES: set(primary),
        speciality.SERVICES_NOT_OFFERED: set(excluded),
    }
    field_for = {
        speciality.SERVICES_OFFERED: "services_offered",
        speciality.PRIMARY_SPECIALITIES: "primary_specialities",
        speciality.SERVICES_NOT_OFFERED: "services_not_offered",
    }
    for question, (minimum, maximum) in selection_limits().items():
        count = len(answers[question])
        if count < minimum:
            errors.add(field_for[question], "too_few", f"Choose at least {minimum}.")
        if maximum is not None and count > maximum:
            errors.add(field_for[question], "too_many", f"Choose at most {maximum}.")

    # The catalog's shared rule set: unknown (incl. other trades'), offered∩excluded, primary⊆offered.
    for conflict in speciality.validate_speciality_answers(answers, allowed):
        code = conflict["code"]
        services = set(conflict["services"])
        if code == "unknown_service":
            for question, selected in answers.items():
                if selected & services:
                    errors.add(field_for[question], "unknown_service", "Choose services of your trade only.")
        elif code == "offered_and_excluded_overlap":
            errors.add("services_not_offered", code, "A service cannot be both offered and not offered.")
        elif code == "primary_not_offered":
            errors.add("primary_specialities", code, "Your main speciality must be one of the services you offer.")
    return errors


def validate_areas(city_code: str | None, area_codes: list[str]) -> FieldErrors:
    errors = FieldErrors({})
    if not city_code:
        errors.add("city", "required", "Choose your city.")
        return errors
    city = City.objects.filter(code=city_code, is_active=True).first()
    if city is None:
        errors.add("city", "unknown_city", "This city is not available.")
        return errors
    if not area_codes:
        errors.add("service_areas", "too_few", "Choose at least one area.")
        return errors
    found = {a.code: a for a in Area.objects.filter(code__in=area_codes, is_active=True).select_related("city")}
    unknown = [code for code in area_codes if code not in found]
    if unknown:
        errors.add("service_areas", "unknown_area", "This area is not available.")
    if any(area.city_id != city.id for area in found.values()):
        errors.add("service_areas", "area_not_in_city", "Choose areas inside the selected city.")
    return errors


def work_issues(profile: WorkerProfile) -> list[str]:
    trade = profile.trade.code if profile.trade else None
    errors = validate_work(
        trade,
        [s.code for s in profile.services_offered.all()],
        [s.code for s in profile.primary_specialities.all()],
        [s.code for s in profile.services_not_offered.all()],
    )
    return sorted({code for items in errors.errors.values() for code, _ in items})


def area_issues(profile: WorkerProfile) -> list[str]:
    city = profile.city.code if profile.city else None
    errors = validate_areas(city, [a.code for a in profile.service_areas.all()])
    return sorted({code for items in errors.errors.values() for code, _ in items})


def onboarding_state(profile: WorkerProfile) -> dict:
    steps = {"work": work_issues(profile), "areas": area_issues(profile)}
    next_step = next((step for step in STEPS if steps[step]), None)
    return {
        "complete": next_step is None,
        "next_step": next_step,
        "steps": {step: {"complete": not issues, "issues": issues} for step, issues in steps.items()},
    }


def is_complete(profile: WorkerProfile) -> bool:
    return not work_issues(profile) and not area_issues(profile)

"""Server-side rules for job request details (JOB-02, JOB-03).

``check(state, complete=...)`` returns ``{field: [(code, message), ...]}``:
- always: catalog entries exist and are active; services/excluded belong to the trade and do not
  overlap; the area belongs to the city; the window ends after it starts, is not in the past and
  starts at most ``MAX_DAYS_AHEAD`` days ahead; text lengths.
- with ``complete=True`` (confirmation): description, trade, at least one service, city, area and
  both window times are required.
Drafts are saved only when the always-rules pass, so a saved draft never holds an invalid
relationship; required fields are only enforced on confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.catalog.models import Area, City, ServiceTag, Trade

MAX_DAYS_AHEAD = 90
MAX_DESCRIPTION = 2000
MAX_PRIVATE_TEXT = 500


@dataclass
class State:
    description: str = ""
    trade: str | None = None
    services: list[str] = field(default_factory=list)
    services_excluded: list[str] = field(default_factory=list)
    city: str | None = None
    area: str | None = None
    preferred_time_text: str = ""
    window_start: datetime | None = None
    window_end: datetime | None = None
    address_private: str = ""
    access_notes: str = ""
    budget_pkr: Decimal | None = None


def check(state: State, *, complete: bool, now: datetime | None = None) -> dict[str, list[tuple[str, str]]]:
    now = now or timezone.now()
    errors: dict[str, list[tuple[str, str]]] = {}

    def add(name: str, code: str, message: str) -> None:
        errors.setdefault(name, []).append((code, message))

    trade = Trade.objects.filter(code=state.trade, is_active=True).first() if state.trade else None
    if state.trade and trade is None:
        add("trade", "unknown_trade", "This trade is not available.")

    for name in ("services", "services_excluded"):
        codes = state.__dict__[name]
        found = {s.code: s for s in ServiceTag.objects.filter(code__in=codes, is_active=True).select_related("trade")}
        if any(code not in found for code in codes):
            add(name, "unknown_service", "This service is not available.")
        elif any(trade is None or found[code].trade_id != trade.id for code in codes):
            add(name, "service_not_in_trade", "Choose services of the selected trade.")
    if set(state.services) & set(state.services_excluded):
        add("services_excluded", "offered_and_excluded_overlap", "A service cannot be both needed and not needed.")

    city = City.objects.filter(code=state.city, is_active=True).first() if state.city else None
    if state.city and city is None:
        add("city", "unknown_city", "This city is not available.")
    area = Area.objects.filter(code=state.area, is_active=True).first() if state.area else None
    if state.area and area is None:
        add("area", "unknown_area", "This area is not available.")
    elif area and city and area.city_id != city.id:
        add("area", "area_not_in_city", "Choose an area inside the selected city.")

    start, end = state.window_start, state.window_end
    if start and end and end <= start:
        add("window_end", "window_end_before_start", "The end time must be after the start time.")
    if start and start < now:
        add("window_start", "window_in_past", "Choose a time that has not passed.")
    if start and start > now + timedelta(days=MAX_DAYS_AHEAD):
        add("window_start", "window_too_far", f"Choose a date within {MAX_DAYS_AHEAD} days.")

    if len(state.description) > MAX_DESCRIPTION:
        add("description", "max_length", "The description is too long.")
    for name in ("address_private", "access_notes"):
        if len(state.__dict__[name]) > MAX_PRIVATE_TEXT:
            add(name, "max_length", "This text is too long.")

    if complete:
        if not state.description.strip():
            add("description", "required", "Describe the job.")
        if not state.trade:
            add("trade", "required", "Choose the trade.")
        if not state.services:
            add("services", "too_few", "Choose at least one service.")
        if not state.city:
            add("city", "required", "Choose the city.")
        if not state.area:
            add("area", "required", "Choose the area.")
        if not start:
            add("window_start", "required", "Choose the date and start time.")
        if not end:
            add("window_end", "required", "Choose the end time.")
    return errors

"""Expected availability of recommended workers for a customer's requested window (informative only).

For each worker the customer sees ONE status and at most one timestamp; never another customer's booking, address,
job or exact times. The calculation uses the worker's reserving bookings (``Booking.RESERVING``: confirmed, arrived,
in progress, completion requested, disputed). Cancelled, completed and closed bookings never hold time.

Statuses, for the requested window ``[start, end)`` (half-open like the booking constraint, so back-to-back is free):
- ``available``: no reserving booking overlaps the rest of the window.
- ``partly_available``: a booking overlaps, but the worker is expected to be free inside the window from ``at``
  (the first free moment, following adjacent bookings).
- ``busy``: bookings cover the rest of the window; ``at`` is the next expected free time after it (adjacent
  reservations are followed, so 4–6 PM then 6–8 PM gives 8 PM).
- ``uncertain``: the worker has a job that is still open after its planned end (they arrived or started and it is not
  finished, confirmed or resolved). Its end is unknown, and the worker cannot start another job until it closes, so no
  time is shown rather than a past or invented one.

This never decides anything and changes no ranking or eligibility. Acceptance and rescheduling keep their own
locked overlap checks (``services._overlaps`` and the ``booking_no_worker_overlap`` constraint), so a stale estimate
cannot book an unavailable worker.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db.models import Q
from django.utils import timezone

from .models import Booking

# Bookings in which the worker has arrived or started: past their planned end they are still running.
STARTED = (Booking.Status.ARRIVED, Booking.Status.IN_PROGRESS, Booking.Status.COMPLETION_REQUESTED, Booking.Status.DISPUTED)
# How far after the requested window adjacent bookings are followed (keeps the batched query bounded).
LOOKAHEAD = timedelta(days=30)


def _iso(value: datetime) -> str:
    return value.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")


def status_for(bookings: list[tuple[datetime, datetime, str]], start: datetime, end: datetime, now: datetime) -> dict:
    """``bookings``: (start_at, end_at, status) of ONE worker's reserving bookings."""
    if any(status in STARTED and e <= now for _, e, status in bookings):
        return {"status": "uncertain", "at": None}
    scheduled = [(s, e) for s, e, _ in bookings]
    first = max(start, now)  # nobody can be free in the past
    if not any(s < end and e > first for s, e in scheduled):
        return {"status": "available", "at": None}
    t = first
    while True:  # follow overlapping and adjacent bookings
        covering = [e for s, e in scheduled if s <= t < e]
        if not covering:
            break
        t = max(covering)
    if t < end:
        return {"status": "partly_available", "at": _iso(t)}
    return {"status": "busy", "at": _iso(t)}


def for_workers(profile_ids, start: datetime, end: datetime, now: datetime | None = None) -> dict[str, dict]:
    """Availability for many workers in ONE query. Returns {worker_profile_id: {"status", "at"}}."""
    ids = [str(pk) for pk in profile_ids]
    if not ids:
        return {}
    now = now or timezone.now()
    rows = (
        Booking.objects.filter(worker_profile_id__in=ids, status__in=Booking.RESERVING)
        .filter(Q(end_at__gt=min(start, now), start_at__lt=end + LOOKAHEAD) | Q(status__in=STARTED, end_at__lte=now))
        .values_list("worker_profile_id", "start_at", "end_at", "status")
    )
    by_worker: dict[str, list] = defaultdict(list)
    for worker_id, s, e, status in rows:
        by_worker[str(worker_id)].append((s, e, status))
    return {pk: status_for(by_worker.get(pk, []), start, end, now) for pk in ids}

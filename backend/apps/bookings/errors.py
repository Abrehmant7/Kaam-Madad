"""Booking API errors. Every 409 carries the current server state needed to recover (``details``)."""

from rest_framework import status

from apps.core.api.exceptions import ApiError


class _Conflict(ApiError):
    status_code = status.HTTP_409_CONFLICT


class QuoteNotCurrent(_Conflict):
    default_code = "quote_not_current"
    default_detail = "This quote version is no longer the current one. Review the latest version."


class QuoteExpired(_Conflict):
    default_code = "quote_expired"
    default_detail = "This quote has expired. Ask the worker to send a new version."


class QuoteNotReady(_Conflict):
    default_code = "quote_not_ready"
    default_detail = "This quote cannot be accepted yet."


class InvitationNotActive(_Conflict):
    default_code = "invitation_not_active"
    default_detail = "This invitation is closed."


class JobAlreadyBooked(_Conflict):
    default_code = "job_already_booked"
    default_detail = "This request is already booked."


class ScheduleConflict(_Conflict):
    default_code = "schedule_conflict"
    default_detail = "The worker is already booked at an overlapping time."


class WorkerNotEligible(_Conflict):
    default_code = "worker_not_eligible"
    default_detail = "This worker cannot take jobs right now."


class IdempotencyKeyReused(_Conflict):
    default_code = "idempotency_key_reused"
    default_detail = "This acceptance key was already used for a different quote."


class InvitationBooked(_Conflict):
    default_code = "invitation_booked"
    default_detail = "This invitation has a booking. Open the booking to cancel or change it."


class BookingStateConflict(_Conflict):
    default_code = "booking_state_conflict"
    default_detail = "This action is not possible in the booking's current state."


class CancelNotAllowed(_Conflict):
    default_code = "cancel_not_allowed"
    default_detail = "The work has started, so the booking can no longer be cancelled here."


class WorkerBusy(_Conflict):
    default_code = "worker_has_job_in_progress"
    default_detail = "Another job of this worker is still in progress. Finish it before starting this one."


class ChangePending(_Conflict):
    default_code = "change_pending"
    default_detail = "A change is already waiting for approval."


class ChangeNotPending(_Conflict):
    default_code = "change_not_pending"
    default_detail = "This change is no longer waiting for approval."


class TimeChangeNotAllowed(_Conflict):
    default_code = "time_change_not_allowed"
    default_detail = "The time can only be changed before the worker arrives."


class NotYourAction(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "not_allowed_for_role"
    default_detail = "The other person in this booking does this."


# Arrival-code errors reuse the phone-confirmation codes (same meaning, same client translations).
class NoActiveCode(ApiError):
    default_code = "no_active_code"
    default_detail = "There is no active arrival code. Ask the customer to show a new code."


class CodeExpired(ApiError):
    default_code = "code_expired"
    default_detail = "This arrival code has expired. Ask the customer for a new code."


class CodeIncorrect(ApiError):
    default_code = "code_incorrect"
    default_detail = "The code is not correct."


class TooManyAttempts(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "too_many_attempts"
    default_detail = "Too many wrong codes. Ask the customer for a new code."

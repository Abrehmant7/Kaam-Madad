"""Application exception types that render through the shared error envelope."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException

from . import errors


class ApiError(APIException):
    """Base class for application errors with a stable code and optional details.

    ``details`` must contain only non-sensitive, client-safe data (for example
    the current server state returned with a 409 conflict).
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = errors.BAD_REQUEST
    default_detail = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(detail=message, code=code)
        self.details = details
        if status_code is not None:
            self.status_code = status_code


class ServiceNotReady(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = errors.SERVICE_NOT_READY
    default_detail = "The service is temporarily unavailable. Please try again shortly."

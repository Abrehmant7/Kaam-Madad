"""The shared API error envelope (requirements §10).

Every API error response has this shape::

    {
      "error": {
        "code": "validation_error",          # stable, machine-readable; clients translate by code
        "message": "Some submitted values are invalid.",   # readable English fallback
        "request_id": "4f0c...",            # same value as the X-Request-ID header
        "fields": {                          # only for field-level validation errors
          "phone_number": [{"code": "invalid_pk_mobile", "message": "..."}]
        },
        "details": {...}                     # optional, non-sensitive structured context
      }
    }

``message`` never contains exception text, stack traces, SQL, or credentials.
"""

from __future__ import annotations

from typing import Any

from ..request_context import get_request_id

# Stable codes used by the foundation. Feature modules add their own.
VALIDATION_ERROR = "validation_error"
NOT_FOUND = "not_found"
PERMISSION_DENIED = "permission_denied"
BAD_REQUEST = "bad_request"
SERVER_ERROR = "server_error"
SERVICE_NOT_READY = "service_not_ready"

FieldErrors = dict[str, list[dict[str, str]]]


def error_body(
    *,
    code: str,
    message: str,
    request_id: str | None = None,
    fields: FieldErrors | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id if request_id is not None else get_request_id(),
    }
    if fields:
        error["fields"] = fields
    if details:
        error["details"] = details
    return {"error": error}

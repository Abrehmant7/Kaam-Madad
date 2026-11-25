"""DRF exception handler that renders every handled API error in the shared envelope.

Unhandled (non-API) exceptions are not swallowed here: DRF re-raises them so
Django's ``handler500`` returns a generic JSON 500 in production and the debug
page in development. Internal exception text is never placed in a response.
"""

from __future__ import annotations

import math
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler as drf_exception_handler

from . import errors

VALIDATION_MESSAGE = "Some submitted values are invalid."


def api_exception_handler(exc: Exception, context: dict[str, Any]):
    # Normalise Django exceptions the same way DRF does, so we can read codes.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, exceptions.ValidationError):
        response.data = errors.error_body(
            code=errors.VALIDATION_ERROR,
            message=VALIDATION_MESSAGE,
            fields=flatten_field_errors(exc.detail),
        )
        return response

    code, message = _code_and_message(exc)
    details = getattr(exc, "details", None)
    if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
        details = {**(details or {}), "retry_after_seconds": math.ceil(exc.wait)}
    response.data = errors.error_body(code=code, message=message, details=details)
    return response


def _code_and_message(exc: Exception) -> tuple[str, str]:
    detail = getattr(exc, "detail", None)
    default_code = getattr(exc, "default_code", errors.BAD_REQUEST)
    if isinstance(detail, exceptions.ErrorDetail):
        return (detail.code or default_code), str(detail)
    if isinstance(detail, str):
        return default_code, detail
    return default_code, str(getattr(exc, "default_detail", "The request could not be processed."))


def flatten_field_errors(detail: Any, prefix: str = "") -> errors.FieldErrors:
    """Flatten DRF's nested validation detail into ``{"a.0.b": [{code, message}]}``.

    Errors that are not tied to a field use DRF's ``non_field_errors`` key.
    """
    result: errors.FieldErrors = {}
    key = prefix or api_settings.NON_FIELD_ERRORS_KEY

    if isinstance(detail, dict):
        for name, value in detail.items():
            child = f"{prefix}.{name}" if prefix else str(name)
            _merge(result, flatten_field_errors(value, child))
    elif isinstance(detail, list):
        for index, item in enumerate(detail):
            if isinstance(item, (dict, list)):
                child = f"{prefix}.{index}" if prefix else str(index)
                _merge(result, flatten_field_errors(item, child))
            else:
                result.setdefault(key, []).append(_leaf(item))
    elif detail is not None:
        result.setdefault(key, []).append(_leaf(detail))
    return result


def _leaf(item: Any) -> dict[str, str]:
    code = getattr(item, "code", None) or "invalid"
    return {"code": code, "message": str(item)}


def _merge(into: errors.FieldErrors, other: errors.FieldErrors) -> None:
    for name, items in other.items():
        into.setdefault(name, []).extend(items)

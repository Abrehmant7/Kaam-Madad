"""Logging helpers."""

import logging

from .request_context import get_request_id


class RequestIDLogFilter(logging.Filter):
    """Attach the current request ID (or "-") to every log record.

    Django logs 4xx/5xx responses (logger ``django.request``) after the
    middleware chain has returned, so fall back to the ``request`` object Django
    attaches to those records.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = get_request_id()
        if request_id is None:
            request_id = getattr(getattr(record, "request", None), "request_id", None)
        record.request_id = request_id or "-"
        return True

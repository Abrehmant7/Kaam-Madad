"""Per-request context shared with logging and error responses."""

from __future__ import annotations

from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Return the current request's ID, or None outside a request."""
    return _request_id.get()


def set_request_id(value: str | None):
    """Set the current request ID; returns a token for ``reset_request_id``."""
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)

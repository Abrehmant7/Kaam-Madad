"""Session authentication for the API.

Differences from DRF's SessionAuthentication:
- CSRF is enforced on EVERY unsafe request (POST/PUT/PATCH/DELETE), including
  anonymous ones such as signup and login. DRF's default only checks CSRF once a
  user is authenticated, which would leave login CSRF open.
- A missing/expired session yields 401 ``not_authenticated`` (via
  ``authenticate_header``) instead of 403, so clients can tell "please log in"
  apart from "you are not allowed".
- Inactive (suspended) users are treated as anonymous.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.authentication import CSRFCheck, SessionAuthentication
from rest_framework.permissions import SAFE_METHODS

from apps.core.api.exceptions import ApiError


class CsrfFailed(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "csrf_failed"
    default_detail = "Security check failed. Refresh the page and try again."


def enforce_csrf(request) -> None:
    def _get_response(_request):  # pragma: no cover - never called
        return None

    check = CSRFCheck(_get_response)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        # The detailed reason stays server-side; clients get a stable code.
        raise CsrfFailed()


class CsrfEnforcedSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        if request.method not in SAFE_METHODS:
            enforce_csrf(request._request)
        user = getattr(request._request, "user", None)
        if not user or not user.is_authenticated or not user.is_active:
            return None
        return (user, None)

    def authenticate_header(self, request) -> str:
        return "Session"

"""Non-DRF views: the single-page-app entry point and API-aware error handlers."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.utils.cache import patch_cache_control
from django.views import defaults
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe

from .api import errors

API_PREFIX = "/api/"


def _is_api_request(request) -> bool:
    return request.path.startswith(API_PREFIX)


def _api_error(request, *, status: int, code: str, message: str) -> JsonResponse:
    body = errors.error_body(code=code, message=message, request_id=getattr(request, "request_id", None))
    return JsonResponse(body, status=status)


@csrf_exempt
def api_not_found(request, *args, **kwargs):
    """Catch-all for unknown /api/ paths so they never fall through to the SPA."""
    return _api_error(request, status=404, code=errors.NOT_FOUND, message="No API endpoint matches this path.")


@require_safe
def spa_index(request, *args, **kwargs):
    """Serve the built React app's index.html for client-side routes.

    Hashed assets under /assets/ are served by WhiteNoise. index.html itself is
    always revalidated so a new deployment's asset hashes are picked up.
    """
    index_file = settings.FRONTEND_DIST_DIR / "index.html"
    try:
        content = index_file.read_bytes()
    except FileNotFoundError:
        return HttpResponseNotFound(
            "Frontend build not found. In development, open the Vite dev server "
            "(http://localhost:5173). For a production-style build, run `npm run build` in frontend/.",
            content_type="text/plain; charset=utf-8",
        )
    response = HttpResponse(content, content_type="text/html; charset=utf-8")
    patch_cache_control(response, no_cache=True, private=True)
    return response


# --- Error handlers (used when DEBUG is False) ------------------------------


def handler400(request, exception=None):
    if _is_api_request(request):
        return _api_error(request, status=400, code=errors.BAD_REQUEST, message="The request could not be processed.")
    return defaults.bad_request(request, exception)


def handler403(request, exception=None):
    if _is_api_request(request):
        return _api_error(
            request, status=403, code=errors.PERMISSION_DENIED, message="You do not have permission to do this."
        )
    return defaults.permission_denied(request, exception)


def handler404(request, exception=None):
    if _is_api_request(request):
        return _api_error(request, status=404, code=errors.NOT_FOUND, message="Not found.")
    return defaults.page_not_found(request, exception)


def handler500(request):
    if _is_api_request(request):
        return _api_error(
            request, status=500, code=errors.SERVER_ERROR, message="Something went wrong on the server. Please try again."
        )
    return defaults.server_error(request)

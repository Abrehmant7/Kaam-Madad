"""Request ID middleware.

Every request gets a server-generated UUID, exposed as ``request.request_id``,
included in log lines, in API error bodies, and in the ``X-Request-ID`` response
header. Client-supplied IDs are deliberately ignored so log correlation cannot
be spoofed or used for log injection.
"""

from __future__ import annotations

import uuid

from .request_context import reset_request_id, set_request_id

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = str(uuid.uuid4())
        request.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)
        response[REQUEST_ID_HEADER] = request_id
        return response

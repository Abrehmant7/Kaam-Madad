"""Liveness and readiness endpoints.

GET /api/v1/health/live/   The process is up and serving requests. Touches no
                           database, session, or external service.
GET /api/v1/health/ready/  The application can serve real traffic: the database
                           accepts a query. Returns 503 with the error envelope
                           when it cannot. Exception details are logged by class
                           name only and never returned to the caller.
"""

from __future__ import annotations

import logging

from django.db import DEFAULT_DB_ALIAS, Error as DatabaseError, connections
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .api.exceptions import ServiceNotReady

logger = logging.getLogger(__name__)

CHECK_OK = "ok"
CHECK_UNAVAILABLE = "unavailable"


def get_database_connection(alias: str = DEFAULT_DB_ALIAS):
    return connections[alias]


def check_database(connection=None) -> bool:
    """Return True if the database answers ``SELECT 1``."""
    connection = connection or get_database_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError as exc:
        # Class name only: driver messages can include host/user details.
        logger.warning("Readiness check failed: database unavailable (%s).", type(exc).__name__)
        return False
    return True


@method_decorator(never_cache, name="dispatch")
class _PublicHealthView(APIView):
    # Public, and must not touch sessions/users (which would hit the database).
    authentication_classes: list = []
    permission_classes = [AllowAny]


class LivenessView(_PublicHealthView):
    def get(self, request):
        return Response({"status": CHECK_OK})


class ReadinessView(_PublicHealthView):
    def get(self, request):
        database_ok = check_database()
        if not database_ok:
            raise ServiceNotReady(details={"checks": {"database": CHECK_UNAVAILABLE}})
        return Response({"status": CHECK_OK, "checks": {"database": CHECK_OK}})

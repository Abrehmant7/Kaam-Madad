"""Account API: CSRF bootstrap, signup, login, logout, current user, language, phone confirmation.

Contracts are documented in docs/api.md.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import ApiError
from config.env import DEPLOYMENT_MODE_DEMO

from . import phone_verification as pv
from .models import User
from .serializers import (
    LanguagePreferenceSerializer,
    LoginSerializer,
    PhoneCodeSerializer,
    SignupSerializer,
    user_payload,
)
from .throttles import LoginIPThrottle, LoginPhoneThrottle, PhoneCodeIPThrottle, SignupIPThrottle

logger = logging.getLogger(__name__)

MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"


class InvalidCredentials(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_credentials"
    default_detail = "The phone number or password is not correct."


class AccountInactive(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "account_inactive"
    default_detail = "This account is not active. Please contact support."


class AlreadyAuthenticated(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "already_authenticated"
    default_detail = "You are already logged in. Log out first to create another account."


@method_decorator([never_cache, ensure_csrf_cookie], name="dispatch")
class CsrfView(APIView):
    """GET /api/v1/auth/csrf/ — sets the csrftoken cookie and returns the token."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@method_decorator(never_cache, name="dispatch")
class MeView(APIView):
    """GET /api/v1/auth/me/ — current session state. Never 401: anonymous is a normal state."""

    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user
        if user and user.is_authenticated:
            return Response({"authenticated": True, "user": user_payload(user)})
        return Response({"authenticated": False, "user": None})


@method_decorator(never_cache, name="dispatch")
class SignupView(APIView):
    """POST /api/v1/auth/signup/ — create a worker/customer account and log it in."""

    permission_classes = [AllowAny]
    throttle_classes = [SignupIPThrottle]

    def post(self, request):
        if request.user and request.user.is_authenticated:
            raise AlreadyAuthenticated()
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                # Only these fields can be set by public signup. Staff flags,
                # verification and restriction state are never client-controlled.
                user = User.objects.create_user(
                    data["phone_number"],
                    data["password"],
                    role=data["role"],
                    preferred_language=data["preferred_language"],
                    is_demo=settings.DEPLOYMENT_MODE == DEPLOYMENT_MODE_DEMO,
                )
        except IntegrityError:
            raise ValidationError(
                {"phone_number": [ErrorDetail("An account with this phone number already exists.", code="phone_taken")]}
            ) from None
        login(request, user, backend=MODEL_BACKEND)
        logger.info("Account created (role=%s, demo=%s).", user.role, user.is_demo)
        return Response({"authenticated": True, "user": user_payload(user)}, status=status.HTTP_201_CREATED)


@method_decorator(never_cache, name="dispatch")
class LoginView(APIView):
    """POST /api/v1/auth/login/ — phone + password; rotates the session and CSRF token."""

    permission_classes = [AllowAny]
    throttle_classes = [LoginIPThrottle, LoginPhoneThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_number = serializer.validated_data["phone_number"]
        password = serializer.validated_data["password"]

        user = authenticate(request, phone_number=phone_number, password=password)
        if user is None:
            # Reveal suspension only to someone who knows the correct password.
            existing = User.objects.filter(phone_number=phone_number).first()
            if existing and not existing.is_active and existing.check_password(password):
                raise AccountInactive()
            raise InvalidCredentials()
        login(request, user)
        return Response({"authenticated": True, "user": user_payload(user)})


@method_decorator(never_cache, name="dispatch")
class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — ends the session. Idempotent (204 even if already logged out)."""

    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(never_cache, name="dispatch")
class LanguagePreferenceView(APIView):
    """PATCH /api/v1/auth/me/language/ — the only profile field editable in M2.

    Role cannot be changed here or anywhere in the public API (AUTH-01).
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = LanguagePreferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.preferred_language = serializer.validated_data["preferred_language"]
        user.save(update_fields=["preferred_language", "updated_at"])
        return Response({"authenticated": True, "user": user_payload(user)})


def _confirmation_state(user: User) -> dict:
    challenge = pv.active_challenge(user)
    return {
        "status": user.phone_confirmation_status,
        "method": user.phone_confirmation_method or None,
        "confirmed_at": user.phone_confirmed_at.isoformat() if user.phone_confirmed_at else None,
        "provider": pv.provider_status(),
        "active_code": pv.challenge_payload(challenge, user) if challenge else None,
    }


@method_decorator(never_cache, name="dispatch")
class PhoneConfirmationView(APIView):
    """GET: confirmation status. POST: issue a new code (supersedes any open code)."""

    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        return [PhoneCodeIPThrottle()] if self.request.method == "POST" else []

    def get(self, request):
        return Response(_confirmation_state(request.user))

    def post(self, request):
        result = pv.start_phone_confirmation(request.user)
        body = _confirmation_state(request.user)
        if result.demo_code is not None:
            # Only the demo sender reveals the code, and only in demo deployments.
            body["demo"] = {
                "code": result.demo_code,
                "notice": "DEMO ONLY: no SMS was sent. This simulated code does not verify phone ownership.",
            }
        return Response(body, status=status.HTTP_201_CREATED)


@method_decorator(never_cache, name="dispatch")
class PhoneConfirmationVerifyView(APIView):
    """POST /api/v1/auth/phone-confirmation/verify/ — submit the 6-digit code."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [PhoneCodeIPThrottle]

    def post(self, request):
        serializer = PhoneCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = pv.verify_phone_confirmation(request.user, serializer.validated_data["code"])
        return Response({"authenticated": True, "user": user_payload(user)})

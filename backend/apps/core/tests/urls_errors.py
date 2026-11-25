"""URLconf used only by error-handling tests."""

from django.urls import include, path
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import ApiError


class _Item(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class _Payload(serializers.Serializer):
    phone_number = serializers.CharField(max_length=5)
    items = _Item(many=True)

    def validate(self, attrs):
        raise serializers.ValidationError("Terms conflict.", code="terms_conflict")


class _PublicView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]


class ValidationView(_PublicView):
    def post(self, request):
        serializer = _Payload(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({})


class ConflictView(_PublicView):
    def post(self, request):
        raise ApiError("Quotation changed.", code="quote_superseded", status_code=409, details={"current_version": 3})


class ProtectedView(APIView):
    """Uses the project defaults: session auth + IsAuthenticated."""

    def get(self, request):
        return Response({"ok": True})


class CrashView(_PublicView):
    def get(self, request):
        raise RuntimeError("secret internal detail: password=hunter2")


def crash_html(request):
    raise RuntimeError("secret internal detail")


test_api = [
    path("validation/", ValidationView.as_view()),
    path("conflict/", ConflictView.as_view()),
    path("protected/", ProtectedView.as_view()),
    path("crash/", CrashView.as_view()),
]

urlpatterns = [
    path("api/v1/test/", include(test_api)),
    path("crash-html/", crash_html),
]

handler500 = "apps.core.views.handler500"

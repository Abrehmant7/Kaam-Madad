"""Test-only URLconf exercising server-side role permissions."""

from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsCustomer, IsMarketplaceUser, IsWorker


class _View(APIView):
    def get(self, request):
        return Response({"ok": True})

    def post(self, request):
        return Response({"ok": True})


class WorkerOnly(_View):
    permission_classes = [IsWorker]


class CustomerOnly(_View):
    permission_classes = [IsCustomer]


class MarketplaceOnly(_View):
    permission_classes = [IsMarketplaceUser]


urlpatterns = [
    path("api/v1/test/worker/", WorkerOnly.as_view()),
    path("api/v1/test/customer/", CustomerOnly.as_view()),
    path("api/v1/test/marketplace/", MarketplaceOnly.as_view()),
]

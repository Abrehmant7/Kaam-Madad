"""Read-only catalog API (public). Only active entries are returned.

Ordering is deterministic: sort_order, then code. List endpoints are paginated
(``page``, ``page_size`` ≤ 200). See docs/api.md for the full contracts.
"""

from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Area, City, ServiceTag, SpecialityQuestion, Trade
from .serializers import (
    AreaSerializer,
    CitySerializer,
    ServiceTagSerializer,
    SpecialityQuestionSerializer,
    TradeSerializer,
)
from .speciality import RULES

MAX_SEARCH_LENGTH = 100


def _codes_param(request, name: str) -> list[str]:
    raw = request.query_params.get(name, "")
    return [code.strip() for code in raw.split(",") if code.strip()][:50]


def _search(queryset, request):
    term = request.query_params.get("search", "").strip()[:MAX_SEARCH_LENGTH]
    if term:
        queryset = queryset.filter(
            Q(label_en__icontains=term) | Q(label_ur__icontains=term) | Q(code__icontains=term)
        )
    return queryset


class _PublicCatalogView(ListAPIView):
    permission_classes = [AllowAny]


class TradeListView(_PublicCatalogView):
    """GET /api/v1/catalog/trades/?search="""

    serializer_class = TradeSerializer

    def get_queryset(self):
        queryset = Trade.objects.filter(is_active=True).annotate(
            service_count=Count("services", filter=Q(services__is_active=True))
        )
        return _search(queryset, self.request).order_by("sort_order", "code")


class ServiceTagListView(_PublicCatalogView):
    """GET /api/v1/catalog/service-tags/?trade=electrician,plumber&search="""

    serializer_class = ServiceTagSerializer

    def get_queryset(self):
        queryset = ServiceTag.objects.filter(is_active=True, trade__is_active=True).select_related("trade")
        trades = _codes_param(self.request, "trade")
        if trades:
            queryset = queryset.filter(trade__code__in=trades)
        return _search(queryset, self.request).order_by("trade__sort_order", "trade__code", "sort_order", "code")


class CityListView(_PublicCatalogView):
    """GET /api/v1/catalog/cities/"""

    serializer_class = CitySerializer

    def get_queryset(self):
        return City.objects.filter(is_active=True).order_by("sort_order", "code")


class AreaListView(_PublicCatalogView):
    """GET /api/v1/catalog/areas/?city=islamabad&kind=sector&search="""

    serializer_class = AreaSerializer

    def get_queryset(self):
        queryset = Area.objects.filter(is_active=True, city__is_active=True).select_related("city")
        cities = _codes_param(self.request, "city")
        if cities:
            queryset = queryset.filter(city__code__in=cities)
        kind = self.request.query_params.get("kind", "").strip()
        if kind:
            queryset = queryset.filter(kind=kind)
        return _search(queryset, self.request).order_by("city__sort_order", "city__code", "sort_order", "code")


class TradeSpecialityQuestionsView(APIView):
    """GET /api/v1/catalog/trades/<code>/speciality-questions/

    The three worker questions for one trade, their choices (the trade's active
    service tags) and the consistency rules between answers.
    """

    permission_classes = [AllowAny]

    def get(self, request, code: str):
        trade = get_object_or_404(Trade, code=code, is_active=True)
        questions = SpecialityQuestion.objects.filter(is_active=True).order_by("sort_order", "code")
        choices = trade.services.filter(is_active=True).order_by("sort_order", "code")
        return Response(
            {
                "trade": TradeSerializer(
                    Trade.objects.filter(pk=trade.pk)
                    .annotate(service_count=Count("services", filter=Q(services__is_active=True)))
                    .get()
                ).data,
                "questions": SpecialityQuestionSerializer(questions, many=True, context={"trade": trade}).data,
                "choices": ServiceTagSerializer(choices, many=True).data,
                "rules": RULES,
            }
        )

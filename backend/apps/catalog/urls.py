from django.urls import path

from . import views

urlpatterns = [
    path("trades/", views.TradeListView.as_view(), name="catalog-trades"),
    path(
        "trades/<slug:code>/speciality-questions/",
        views.TradeSpecialityQuestionsView.as_view(),
        name="catalog-trade-questions",
    ),
    path("service-tags/", views.ServiceTagListView.as_view(), name="catalog-service-tags"),
    path("cities/", views.CityListView.as_view(), name="catalog-cities"),
    path("areas/", views.AreaListView.as_view(), name="catalog-areas"),
]

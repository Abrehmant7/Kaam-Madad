from django.urls import path

from . import views

urlpatterns = [
    path("", views.BlocksView.as_view(), name="blocks"),
    path("<uuid:block_id>/", views.BlockDetailView.as_view(), name="block"),
]

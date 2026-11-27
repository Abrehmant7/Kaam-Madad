from django.urls import path

from . import views

urlpatterns = [
    path("", views.ReportsView.as_view(), name="reports"),
    path("<uuid:report_id>/", views.ReportDetailView.as_view(), name="report"),
    path("<uuid:report_id>/evidence/", views.EvidenceView.as_view(), name="report-evidence"),
    path("<uuid:report_id>/evidence/<uuid:evidence_id>/content/", views.EvidenceContentView.as_view(), name="report-evidence-content"),
    path("<uuid:report_id>/replies/", views.ReplyView.as_view(), name="report-replies"),
]

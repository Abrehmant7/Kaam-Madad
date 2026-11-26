from django.urls import path

from . import views

worker_patterns = [
    path("me/", views.WorkerMeView.as_view(), name="worker-me"),
    path("me/work/", views.WorkStepView.as_view(), name="worker-work"),
    path("me/areas/", views.AreasStepView.as_view(), name="worker-areas"),
    path("me/preferences/", views.PreferencesView.as_view(), name="worker-preferences"),
]

identity_patterns = [
    path("cases/", views.IdentityCasesView.as_view(), name="identity-cases"),
    path("cases/<uuid:case_id>/scan/", views.IdentityScanView.as_view(), name="identity-scan"),
    path("cases/<uuid:case_id>/submit/", views.IdentitySubmitView.as_view(), name="identity-submit"),
]

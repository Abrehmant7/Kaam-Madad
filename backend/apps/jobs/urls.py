from django.urls import path

from . import views

urlpatterns = [
    path("", views.JobListCreateView.as_view(), name="jobs"),
    path("<uuid:job_id>/", views.JobDetailView.as_view(), name="job"),
    path("<uuid:job_id>/source/", views.JobSourceView.as_view(), name="job-source"),
    path("<uuid:job_id>/confirm/", views.JobConfirmView.as_view(), name="job-confirm"),
    path("<uuid:job_id>/photos/", views.JobPhotosView.as_view(), name="job-photos"),
    path("<uuid:job_id>/photos/<uuid:photo_id>/", views.JobPhotoDetailView.as_view(), name="job-photo"),
    path("<uuid:job_id>/photos/<uuid:photo_id>/content/", views.JobPhotoContentView.as_view(), name="job-photo-content"),
]

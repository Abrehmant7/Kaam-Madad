from django.urls import path

from . import views

# Mounted under /api/v1/jobs/ (customer, request owner only).
customer_patterns = [
    path("<uuid:job_id>/recommendations/", views.RecommendationsView.as_view(), name="job-recommendations"),
    path("<uuid:job_id>/shared-description/", views.SharedDescriptionView.as_view(), name="job-shared-description"),
    path("<uuid:job_id>/invitations/", views.JobInvitationsView.as_view(), name="job-invitations"),
    path("<uuid:job_id>/invitations/<uuid:invitation_id>/withdraw/", views.WithdrawView.as_view(), name="job-invitation-withdraw"),
]

# Mounted under /api/v1/invitations/ (worker, invitations addressed to them only).
worker_patterns = [
    path("", views.InboxView.as_view(), name="invitations"),
    path("<uuid:invitation_id>/", views.InvitationDetailView.as_view(), name="invitation"),
    path("<uuid:invitation_id>/decline/", views.DeclineView.as_view(), name="invitation-decline"),
]

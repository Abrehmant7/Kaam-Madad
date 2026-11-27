from django.urls import path

from apps.reviews import views as review_views

from . import views

urlpatterns = [
    path("", views.BookingsView.as_view(), name="bookings"),
    path("feedback/", review_views.WorkerFeedbackView.as_view(), name="worker-feedback"),
    path("<uuid:booking_id>/", views.BookingDetailView.as_view(), name="booking"),
    path("<uuid:booking_id>/arrive/", views.ArriveView.as_view(), name="booking-arrive"),
    path("<uuid:booking_id>/arrival-code/", views.IssueCodeView.as_view(), name="booking-arrival-code"),
    path("<uuid:booking_id>/start/", views.StartView.as_view(), name="booking-start"),
    path("<uuid:booking_id>/cancel/", views.CancelView.as_view(), name="booking-cancel"),
    path("<uuid:booking_id>/changes/", views.ChangesView.as_view(), name="booking-changes"),
    path("<uuid:booking_id>/changes/<uuid:change_id>/approve/", views.ChangeDecisionView.as_view(action="approve"),
         name="booking-change-approve"),
    path("<uuid:booking_id>/changes/<uuid:change_id>/reject/", views.ChangeDecisionView.as_view(action="reject"),
         name="booking-change-reject"),
    path("<uuid:booking_id>/changes/<uuid:change_id>/withdraw/", views.ChangeDecisionView.as_view(action="withdraw"),
         name="booking-change-withdraw"),
    path("<uuid:booking_id>/request-completion/", views.RequestCompletionView.as_view(), name="booking-request-completion"),
    path("<uuid:booking_id>/confirm-completion/", views.ConfirmCompletionView.as_view(), name="booking-confirm-completion"),
    path("<uuid:booking_id>/raise-issue/", views.RaiseIssueView.as_view(), name="booking-raise-issue"),
    path("<uuid:booking_id>/review/", review_views.ReviewView.as_view(), name="booking-review"),
]

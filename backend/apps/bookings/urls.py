from django.urls import path

from . import views

urlpatterns = [
    path("", views.BookingsView.as_view(), name="bookings"),
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
]

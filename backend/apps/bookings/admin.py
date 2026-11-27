"""Bookings in Django Admin: read-only, plus ONE permission-checked staff action (M9) — record the outcome of a
disputed completion (return to in progress, or close without confirmed completion). Broader misconduct
reporting is M10."""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from rest_framework.exceptions import APIException

from . import services
from .models import ArrivalCode, Booking, BookingChange, BookingEvent


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class EventInline(admin.TabularInline):
    model = BookingEvent
    extra = 0
    can_delete = False
    fields = ("at", "kind", "from_status", "to_status", "actor_role", "note")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ResolveDisputeForm(forms.Form):
    outcome = forms.ChoiceField(choices=Booking.StaffOutcome.choices, widget=forms.RadioSelect)
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), min_length=3, max_length=1000,
                             help_text="Shown to both participants. Do not include personal details.")


@admin.register(Booking)
class BookingAdmin(ReadOnly):
    list_display = ("id", "status", "start_at", "end_at", "quote_version", "created_at")
    list_filter = ("status",)
    readonly_fields = ("dispute_action", "job", "invitation", "quote", "quote_version", "customer", "worker_profile", "status",
                       "start_at", "end_at", "accepted_terms", "terms", "created_at", "arrived_at", "started_at",
                       "completion_requested_at", "completed_at", "disputed_at", "dispute_reason", "dispute_note",
                       "staff_outcome", "staff_reason", "staff_at", "closed_at", "cancelled_at", "cancelled_role",
                       "cancel_reason", "cancel_note")
    exclude = ("idempotency_key", "cancelled_by", "staff_by", "completed_services")
    inlines = [EventInline]

    @admin.display(description="Dispute")
    def dispute_action(self, obj):
        if obj.status != Booking.Status.DISPUTED:
            return "—"
        url = reverse("admin:bookings_booking_resolve", args=[obj.pk])
        return format_html('<a class="button" href="{}">Record dispute outcome</a>', url)

    def get_urls(self):
        extra = [path("<uuid:object_id>/resolve-dispute/", self.admin_site.admin_view(self.resolve_view),
                      name="bookings_booking_resolve")]
        return extra + super().get_urls()

    def resolve_view(self, request, object_id):
        if not request.user.has_perm("bookings.resolve_dispute"):
            raise PermissionDenied
        booking = get_object_or_404(Booking, pk=object_id)
        form = ResolveDisputeForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                services.staff_resolve(request.user, booking.pk, outcome=form.cleaned_data["outcome"],
                                       reason=form.cleaned_data["reason"])
            except APIException as exc:
                messages.error(request, f"Not recorded: {exc.detail}")
            else:
                messages.success(request, "Dispute outcome recorded.")
                return redirect(reverse("admin:bookings_booking_change", args=[booking.pk]))
        context = {**self.admin_site.each_context(request), "opts": self.model._meta, "booking": booking, "form": form,
                   "title": "Record dispute outcome"}
        return TemplateResponse(request, "admin/bookings/resolve_dispute.html", context)


@admin.register(ArrivalCode)
class ArrivalCodeAdmin(ReadOnly):
    list_display = ("booking", "issued_at", "expires_at", "failed_attempts", "used_at", "invalidated_at")
    exclude = ("digest",)  # never shown, even to staff


@admin.register(BookingChange)
class BookingChangeAdmin(ReadOnly):
    list_display = ("booking", "number", "status", "proposed_role", "created_at", "decided_at")

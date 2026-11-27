"""Read-only admin views of bookings (staff resolution actions arrive with M9/M10)."""

from django.contrib import admin

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


@admin.register(Booking)
class BookingAdmin(ReadOnly):
    list_display = ("id", "status", "start_at", "end_at", "quote_version", "created_at")
    list_filter = ("status",)
    readonly_fields = ("job", "invitation", "quote", "quote_version", "customer", "worker_profile", "status", "start_at",
                       "end_at", "accepted_terms", "terms", "created_at", "arrived_at", "started_at", "cancelled_at",
                       "cancelled_role", "cancel_reason", "cancel_note")
    exclude = ("idempotency_key", "cancelled_by")
    inlines = [EventInline]


@admin.register(ArrivalCode)
class ArrivalCodeAdmin(ReadOnly):
    list_display = ("booking", "issued_at", "expires_at", "failed_attempts", "used_at", "invalidated_at")
    exclude = ("digest",)  # never shown, even to staff


@admin.register(BookingChange)
class BookingChangeAdmin(ReadOnly):
    list_display = ("booking", "number", "status", "proposed_role", "created_at", "decided_at")

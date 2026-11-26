"""Read-only staff view of invitations (no private job details)."""

from django.contrib import admin

from .models import Invitation


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "worker_profile", "status", "created_at", "seen_at", "closed_at")
    list_filter = ("status",)
    ordering = ("-created_at",)
    fields = ("job", "worker_profile", "status", "decline_reason", "created_at", "seen_at", "closed_at", "shared_summary")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

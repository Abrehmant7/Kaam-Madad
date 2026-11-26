"""Read-only staff view of job requests. Private address and access notes are not shown."""

from django.contrib import admin

from .models import JobRequest


@admin.register(JobRequest)
class JobRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "status", "trade", "area", "window_start", "updated_at")
    list_filter = ("status", "trade", "city")
    ordering = ("-updated_at",)
    fields = ("customer", "status", "source_kind", "source_language", "description", "trade", "services",
              "services_excluded", "city", "area", "preferred_time_text", "window_start", "window_end", "budget_pkr",
              "confirmed_at", "created_at", "updated_at")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

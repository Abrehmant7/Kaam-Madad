"""Minimal staff views (read-only). Staff decisions (manual review, suspension) are a later module."""

from django.contrib import admin

from apps.workers.onboarding import is_complete

from .models import DemoIdentityRecord, IdentityVerification, WorkerProfile


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IdentityVerification)
class IdentityVerificationAdmin(ReadOnlyAdmin):
    list_display = ("user", "status", "method", "ocr_source", "registry_source", "cnic_masked", "created_at", "decided_at")
    list_filter = ("status", "method", "registry_outcome", "registry_simulated")
    search_fields = ("registry_reference",)
    ordering = ("-created_at",)
    # Never the digest or the pending OCR draft. No image exists: scans are not stored.
    fields = (
        "user", "status", "method", "consent_given_at", "consent_version",
        "scan_count", "scanned_at", "scan_mime_type", "scan_width", "scan_height",
        "ocr_status", "ocr_provider", "ocr_engine", "ocr_rotation", "ocr_failure_reason",
        "cnic_masked", "name_corrected", "number_corrected", "submitted_at", "submission_count",
        "registry_outcome", "registry_provider", "registry_reference", "registry_simulated", "registry_checked_at",
        "decided_at", "reviewer", "review_note", "created_at", "updated_at",
    )
    readonly_fields = fields

    @admin.display(description="OCR source")
    def ocr_source(self, obj):
        return f"{obj.ocr_provider} ({obj.ocr_status})" if obj.ocr_provider else "—"

    @admin.display(description="Registry source")
    def registry_source(self, obj):
        if not obj.registry_provider:
            return "—"
        return f"{obj.registry_provider} (demo, fictional)" if obj.registry_simulated else obj.registry_provider


@admin.register(WorkerProfile)
class WorkerProfileAdmin(ReadOnlyAdmin):
    list_display = ("user", "trade", "city", "complete", "accepting_requests", "updated_at")
    list_filter = ("trade", "city", "accepting_requests")
    fields = ("user", "trade", "services_offered", "primary_specialities", "services_not_offered", "city",
              "service_areas", "accepting_requests", "work_saved_at", "areas_saved_at", "created_at", "updated_at")
    readonly_fields = fields

    @admin.display(boolean=True, description="Profile complete")
    def complete(self, obj):
        return is_complete(obj)


@admin.register(DemoIdentityRecord)
class DemoIdentityRecordAdmin(ReadOnlyAdmin):
    list_display = ("reference", "full_name_en", "full_name_ur", "cnic_masked", "demo_address", "is_active")
    fields = ("reference", "full_name_en", "full_name_ur", "cnic_masked", "demo_address", "is_active", "created_at",
              "updated_at")
    readonly_fields = fields

"""Read-only staff views (no audio, no private job details)."""

from django.contrib import admin

from .models import GapFinding, Message, Quote


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Message)
class MessageAdmin(ReadOnly):
    list_display = ("id", "invitation", "sender_role", "kind", "caption_status", "created_at")
    list_filter = ("kind", "caption_status")
    fields = ("invitation", "sender_role", "kind", "text", "caption_status", "interpreted_text", "created_at")
    readonly_fields = fields


@admin.register(Quote)
class QuoteAdmin(ReadOnly):
    list_display = ("id", "invitation", "version", "status", "check_status", "submitted_at", "expires_at")
    list_filter = ("status", "check_status")
    fields = ("invitation", "version", "status", "inspection_only", "scope", "quantity", "labour_amount", "labour_basis",
              "materials", "materials_amount", "visit_fee", "visit_fee_treatment", "exclusions", "start_at", "end_at",
              "totals", "submitted_at", "superseded_at", "expires_at", "check_status", "check_provider", "check_simulated",
              "checked_at", "manual_review_at")
    readonly_fields = fields


@admin.register(GapFinding)
class GapFindingAdmin(ReadOnly):
    list_display = ("id", "quote", "source", "code", "blocking", "status", "resolution", "resolved_role")
    list_filter = ("source", "status", "code")
    fields = ("quote", "source", "code", "blocking", "question", "ask", "sources", "status", "resolution", "resolution_note",
              "resolved_role", "resolved_at", "created_at")
    readonly_fields = fields

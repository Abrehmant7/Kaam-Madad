"""Staff queue for misconduct reports (M10, REP-02). Follows the M9 pattern: read-only model admin plus
permission-checked form views that call the service layer.

Permissions (assign per staff user or group):
- ``reports.review_report``      — see the queue and report text, record decisions and messages;
- ``reports.view_evidence``      — open evidence (every opening is recorded in EvidenceAccess);
- ``reports.take_account_action``— restrict / lift / suspend / reactivate the REPORTED account (with a reason).
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from rest_framework.exceptions import APIException

from . import services
from .models import ContactBlock, Report, ReportDecision, ReportMessage
from .views import evidence_file_response


class NoEdit:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class MessageInline(NoEdit, admin.TabularInline):
    model = ReportMessage
    extra = 0
    fields = ("created_at", "kind", "text")
    readonly_fields = fields
    verbose_name_plural = "Messages (internal notes are never shown to the reporter)"


class DecisionInline(NoEdit, admin.TabularInline):
    model = ReportDecision
    extra = 0
    fields = ("at", "action", "actor", "reason", "old_state", "new_state")
    readonly_fields = fields
    verbose_name_plural = "Decisions (audit log)"


DECISIONS = [
    ("note", "Internal note only (no status change)"),
    ("mark_reviewing", "Mark as reviewing"),
    ("request_info", "Ask the reporter for more information"),
    ("resolve", "Resolve"),
    ("dismiss", "Dismiss"),
]
ACCOUNT_ACTIONS = [
    ("", "No account action"),
    ("restrict", "Restrict the reported account (can still sign in, view records and report)"),
    ("lift_restriction", "Lift the restriction"),
    ("suspend", "Suspend the reported account (no login)"),
    ("reactivate", "Reactivate the reported account"),
]


class DecisionForm(forms.Form):
    action = forms.ChoiceField(choices=DECISIONS, widget=forms.RadioSelect)
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), min_length=3, max_length=1000,
                             help_text="Audit reason (staff only).")
    message_to_reporter = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, max_length=2000,
                                          help_text="Shown to the reporter only. Required to ask for information, resolve or dismiss.")
    internal_note = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False, max_length=2000,
                                    help_text="Never shown to the reporter or the reported person.")
    account_action = forms.ChoiceField(choices=ACCOUNT_ACTIONS, required=False,
                                       help_text="Needs the 'take account action' permission.")
    account_reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False, max_length=1000)


@admin.register(Report)
class ReportAdmin(NoEdit, admin.ModelAdmin):
    list_display = ("id", "category", "status", "awaiting_reply", "reporter_role", "created_at")
    list_filter = ("status", "category", "awaiting_reply", ("created_at", admin.DateFieldListFilter))
    date_hierarchy = "created_at"
    readonly_fields = ("actions_link", "status", "category", "reporter_role", "interaction", "reported_account",
                       "description", "evidence_list", "awaiting_reply", "created_at", "closed_at")
    exclude = ("reporter", "reported", "invitation", "booking", "client_id")
    inlines = [MessageInline, DecisionInline]

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff and request.user.has_perm("reports.review_report")

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    @admin.display(description="Decide")
    def actions_link(self, obj):
        return format_html('<a class="button" href="{}">Record a decision…</a>', reverse("admin:reports_report_decide", args=[obj.pk]))

    @admin.display(description="Interaction")
    def interaction(self, obj):
        links = [format_html('<a href="{}">Invitation</a>', reverse("admin:invitations_invitation_change", args=[obj.invitation_id]))]
        if obj.booking_id:
            links.append(format_html('<a href="{}">Booking</a>', reverse("admin:bookings_booking_change", args=[obj.booking_id])))
        return format_html_join(" · ", "{}", ((link,) for link in links))

    @admin.display(description="Reported account")
    def reported_account(self, obj):
        user = obj.reported
        state = "suspended" if not user.is_active else ("restricted" if user.restricted_at else "active")
        return f"{user.role or 'staff'} · {user.masked_phone_number} · {state}"

    @admin.display(description="Evidence")
    def evidence_list(self, obj):
        items = list(obj.evidence.all())
        if not items:
            return "—"
        return format_html_join(
            format_html("<br>"), '{} {} · {} bytes {}',
            ((item.get_role_display(), item.kind, item.size_bytes,
              "(removed under retention)" if item.deleted_at else
              format_html('<a href="{}">Open (recorded)</a>', reverse("admin:reports_report_evidence", args=[obj.pk, item.pk])))
             for item in items),
        )

    def get_urls(self):
        extra = [
            path("<uuid:object_id>/decide/", self.admin_site.admin_view(self.decide_view), name="reports_report_decide"),
            path("<uuid:object_id>/evidence/<uuid:evidence_id>/", self.admin_site.admin_view(self.evidence_view),
                 name="reports_report_evidence"),
        ]
        return extra + super().get_urls()

    def decide_view(self, request, object_id):
        if not request.user.has_perm("reports.review_report"):
            raise PermissionDenied
        report = get_object_or_404(Report, pk=object_id)
        form = DecisionForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                services.decide(request.user, report.pk, **form.cleaned_data)
            except APIException as exc:
                messages.error(request, f"Not recorded: {exc.detail}")
            else:
                messages.success(request, "Decision recorded.")
                return redirect(reverse("admin:reports_report_change", args=[report.pk]))
        context = {**self.admin_site.each_context(request), "opts": self.model._meta, "report": report, "form": form,
                   "title": "Record a decision"}
        return TemplateResponse(request, "admin/reports/decide.html", context)

    def evidence_view(self, request, object_id, evidence_id):
        try:
            item = services.open_evidence_for_staff(request.user, evidence_id)  # permission check + access record
        except APIException:
            raise PermissionDenied from None
        if str(item.report_id) != str(object_id):
            raise PermissionDenied
        return evidence_file_response(item)


@admin.register(ContactBlock)
class ContactBlockAdmin(NoEdit, admin.ModelAdmin):
    list_display = ("id", "created_at")
    readonly_fields = ("created_at", "invitation")
    exclude = ("blocker", "blocked")

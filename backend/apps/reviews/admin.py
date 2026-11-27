"""Reviews in Django Admin: read-only, plus a permission-checked "hide with a reason" action (REV-02).
The original text is never edited."""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from rest_framework.exceptions import APIException

from . import services
from .models import Review


class HideReviewForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), min_length=3, max_length=1000,
                             help_text="Recorded for audit.")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "rating", "source", "created_at", "hidden_at")
    list_filter = ("rating", "hidden_at")
    readonly_fields = ("hide_action", "booking", "worker_profile", "rating", "text", "source", "interpreted_text", "services",
                       "created_at", "hidden_at", "hidden_by", "hidden_reason")
    exclude = ("customer", "audio_clip")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Moderation")
    def hide_action(self, obj):
        if obj.hidden_at:
            return "Hidden"
        return format_html('<a class="button" href="{}">Hide review…</a>', reverse("admin:reviews_review_hide", args=[obj.pk]))

    def get_urls(self):
        extra = [path("<uuid:object_id>/hide/", self.admin_site.admin_view(self.hide_view), name="reviews_review_hide")]
        return extra + super().get_urls()

    def hide_view(self, request, object_id):
        if not request.user.has_perm("reviews.hide_review"):
            raise PermissionDenied
        review = get_object_or_404(Review, pk=object_id)
        form = HideReviewForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                services.hide_review(request.user, review.pk, form.cleaned_data["reason"])
            except APIException as exc:
                messages.error(request, f"Not hidden: {exc.detail}")
            else:
                messages.success(request, "Review hidden.")
                return redirect(reverse("admin:reviews_review_change", args=[review.pk]))
        context = {**self.admin_site.each_context(request), "opts": self.model._meta, "review": review, "form": form,
                   "title": "Hide review"}
        return TemplateResponse(request, "admin/reviews/hide_review.html", context)

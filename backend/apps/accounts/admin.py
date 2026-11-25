from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .forms import UserChangeForm, UserCreationForm
from .models import PhoneVerificationChallenge, User
from .phone import mask_phone_number, normalize_pk_mobile_number


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Staff management of accounts.

    Lists show masked phone numbers; the full number is visible only on a
    user's own change page to staff with permission to view users.
    """

    form = UserChangeForm
    add_form = UserCreationForm

    list_display = (
        "masked_phone_number",
        "role",
        "preferred_language",
        "is_active",
        "is_staff",
        "is_demo",
        "date_joined",
    )
    list_filter = (
        "role",
        "is_active",
        "is_staff",
        "is_superuser",
        "is_demo",
        "phone_confirmation_method",
        "preferred_language",
    )
    search_fields = ("phone_number",)
    search_help_text = _("Search by phone number, in any format (e.g. 0300 1234567).")
    ordering = ("-date_joined",)
    readonly_fields = (
        "id",
        "last_login",
        "date_joined",
        "updated_at",
        "phone_confirmed_at",
        "phone_confirmation_method",
    )

    fieldsets = (
        (None, {"fields": ("id", "phone_number", "password")}),
        (_("Marketplace"), {"fields": ("role", "preferred_language", "is_demo")}),
        (
            _("Phone confirmation (not legal identity)"),
            {"fields": ("phone_confirmed_at", "phone_confirmation_method")},
        ),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "phone_number",
                    "role",
                    "preferred_language",
                    "is_demo",
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    @admin.display(description=_("phone number"), ordering="phone_number")
    def masked_phone_number(self, obj: User) -> str:
        return obj.masked_phone_number

    def get_search_results(self, request, queryset, search_term):
        # A complete number in any accepted format matches exactly after normalisation.
        try:
            normalized = normalize_pk_mobile_number(search_term)
        except ValidationError:
            return super().get_search_results(request, queryset, search_term)
        return queryset.filter(phone_number=normalized), False


@admin.register(PhoneVerificationChallenge)
class PhoneVerificationChallengeAdmin(admin.ModelAdmin):
    """Read-only audit view of issued codes. The code digest is never displayed."""

    list_display = ("created_at", "masked_phone", "purpose", "method", "attempt_count", "max_attempts",
                    "expires_at", "consumed_at", "invalidated_at", "invalidation_reason")
    list_filter = ("purpose", "method", "invalidation_reason")
    ordering = ("-created_at",)
    fields = ("id", "user", "masked_phone", "purpose", "method", "provider_reference", "created_at",
              "expires_at", "attempt_count", "max_attempts", "consumed_at", "invalidated_at",
              "invalidation_reason")
    readonly_fields = fields

    @admin.display(description=_("phone number"))
    def masked_phone(self, obj):
        return mask_phone_number(obj.phone_number)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

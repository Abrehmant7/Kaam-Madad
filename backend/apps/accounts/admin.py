from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .forms import UserChangeForm, UserCreationForm
from .models import User
from .phone import normalize_pk_mobile_number


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
    list_filter = ("role", "is_active", "is_staff", "is_superuser", "is_demo", "preferred_language")
    search_fields = ("phone_number",)
    search_help_text = _("Search by phone number, in any format (e.g. 0300 1234567).")
    ordering = ("-date_joined",)
    readonly_fields = ("id", "last_login", "date_joined", "updated_at")

    fieldsets = (
        (None, {"fields": ("id", "phone_number", "password")}),
        (_("Marketplace"), {"fields": ("role", "preferred_language", "is_demo")}),
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

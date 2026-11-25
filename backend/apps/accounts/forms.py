"""Admin forms for the phone-number-based user model."""

from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm as DjangoUserChangeForm

from .models import User
from .phone import normalize_pk_mobile_number


class PhoneNumberFormField(forms.CharField):
    """Accepts any supported input format and cleans it to +923XXXXXXXXX."""

    def __init__(self, **kwargs):
        # The stored value is 13 characters; typed input may include spaces/dashes.
        kwargs["max_length"] = 32
        super().__init__(**kwargs)
        self.widget.attrs.update({"inputmode": "tel", "autocomplete": "off", "dir": "ltr"})

    def to_python(self, value):
        value = super().to_python(value)
        if value in self.empty_values:
            return value
        return normalize_pk_mobile_number(value)


class UserCreationForm(AdminUserCreationForm):
    class Meta:
        model = User
        fields = ("phone_number", "role", "preferred_language", "is_demo")
        field_classes = {"phone_number": PhoneNumberFormField}


class UserChangeForm(DjangoUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"
        field_classes = {"phone_number": PhoneNumberFormField}

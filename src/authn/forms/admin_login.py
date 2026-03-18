"""
Admin login forms for the two-step email verification code flow.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

Member = get_user_model()


class AdminEmailForm(forms.Form):
    """Step 1: email entry."""

    email = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"placeholder": _("Email"), "autofocus": True}),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        member = Member.objects.filter(email__iexact=email, is_staff=True, is_active=True).first()
        if member is None:
            raise forms.ValidationError(_("Unable to send verification code."))
        self.cleaned_data["member"] = member
        return email


class AdminCodeForm(forms.Form):
    """Step 2: 6-digit verification code entry."""

    code = forms.CharField(
        label=_("Verification code"),
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "placeholder": _("000000"),
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
                "autocomplete": "one-time-code",
                "autofocus": True,
            }
        ),
    )

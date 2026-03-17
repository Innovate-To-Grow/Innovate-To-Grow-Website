"""
Form for accepting an admin invitation and creating a staff/superuser account.
"""

import re

from django import forms
from django.contrib.auth import get_user_model, password_validation

Member = get_user_model()

HTML_TAG_RE = re.compile(r"<[^>]+>")


class AcceptInvitationForm(forms.Form):
    email = forms.EmailField(
        disabled=True,
        widget=forms.EmailInput(
            attrs={
                "class": "border bg-base-50 font-medium min-w-full rounded-md text-font-default-light text-sm px-3 py-2 dark:bg-base-900 dark:text-font-default-dark",
                "readonly": "readonly",
            }
        ),
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "border bg-white font-medium min-w-full rounded-md text-font-default-light text-sm px-3 py-2 dark:bg-base-900 dark:text-font-default-dark",
                "placeholder": "Username",
            }
        ),
    )
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "border bg-white font-medium min-w-full rounded-md text-font-default-light text-sm px-3 py-2 dark:bg-base-900 dark:text-font-default-dark",
                "placeholder": "First name",
            }
        ),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "border bg-white font-medium min-w-full rounded-md text-font-default-light text-sm px-3 py-2 dark:bg-base-900 dark:text-font-default-dark",
                "placeholder": "Last name",
            }
        ),
    )
    organization = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "border bg-white font-medium min-w-full rounded-md text-font-default-light text-sm px-3 py-2 dark:bg-base-900 dark:text-font-default-dark",
                "placeholder": "Organization (optional)",
            }
        ),
    )
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "border bg-white font-medium min-w-full rounded-md text-font-default-light text-sm px-3 py-2 dark:bg-base-900 dark:text-font-default-dark",
                "placeholder": "Password",
                "autocomplete": "new-password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "border bg-white font-medium min-w-full rounded-md text-font-default-light text-sm px-3 py-2 dark:bg-base-900 dark:text-font-default-dark",
                "placeholder": "Confirm password",
                "autocomplete": "new-password",
            }
        ),
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if Member.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_first_name(self):
        value = self.cleaned_data["first_name"]
        if HTML_TAG_RE.search(value):
            raise forms.ValidationError("HTML tags are not allowed.")
        return value

    def clean_last_name(self):
        value = self.cleaned_data["last_name"]
        if HTML_TAG_RE.search(value):
            raise forms.ValidationError("HTML tags are not allowed.")
        return value

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1:
            password_validation.validate_password(p1)
        return cleaned

"""
Admin forms for authn app.
"""

from django import forms
from django.apps import apps as django_apps
from django.contrib import admin
from django.contrib.auth.forms import SetPasswordMixin
from django.core.exceptions import ValidationError
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from unfold.forms import UserChangeForm, UserCreationForm

from ....models import Member
from ....services.members.profile_image import ALLOWED_CONTENT_TYPES
from ..shared.help_texts import MEMBER_HELP_TEXTS, MEMBER_LABELS
from .profile_image import Base64ImageField, Base64ImageWidget


def admin_app_choices():
    """(app_label, verbose_name) choices for every Django app with registered admin models.

    Computed lazily (call at form ``__init__`` time, not import time) so the admin
    registry is fully populated. This is the menu of apps a member's ``admin_apps``
    grant can draw from — see apps.core.utils.access.user_can_access_app.
    """
    labels = sorted({model._meta.app_label for model in admin.site._registry})
    choices = []
    for label in labels:
        try:
            verbose = django_apps.get_app_config(label).verbose_name
        except LookupError:
            verbose = label
        choices.append((label, f"{verbose} ({label})"))
    return choices


class MemberCreationForm(UserCreationForm):
    """User creation form for the Member model with Unfold-styled password widgets.

    Passwords are optional: leave both blank to create the member with an unusable password
    (set a password later or use other auth). If either field is set, both must match.
    """

    class Meta(UserCreationForm.Meta):
        model = Member
        fields = ()
        labels = MEMBER_LABELS
        help_texts = MEMBER_HELP_TEXTS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The stock AdminUserCreationForm includes usable_password, but MemberAdmin.add_fieldsets
        # does not — leaving defaults would still require a password. Drop the field and use
        # validate_passwords() below.
        if "usable_password" in self.fields:
            del self.fields["usable_password"]
        self.fields["password1"].help_text = _(
            "Optional. If left empty, the member cannot sign in with a password until you set one (or they use other login methods)."
        )
        self.fields["password2"].help_text = _("Optional. Must match the password field if you enter a password.")

    def validate_passwords(
        self,
        password1_field_name="password1",
        password2_field_name="password2",
    ):
        p1 = self.cleaned_data.get(password1_field_name) or ""
        p2 = self.cleaned_data.get(password2_field_name) or ""
        if not p1 and not p2:
            self.cleaned_data["set_usable_password"] = False
            return
        if bool(p1) != bool(p2):
            self.add_error(
                password2_field_name,
                ValidationError(
                    _("Enter the same password in both fields, or leave both empty."),
                    code="password_incomplete",
                ),
            )
            return
        self.cleaned_data["set_usable_password"] = True
        self.cleaned_data[password1_field_name] = p1
        self.cleaned_data[password2_field_name] = p2
        SetPasswordMixin.validate_passwords(self, password1_field_name, password2_field_name)


class MemberChangeForm(UserChangeForm):
    """User change form for the Member model with Unfold-styled password widget."""

    # Per-app admin grant. ``admin_apps`` is a JSONField (list of app labels), so it
    # cannot use admin ``filter_horizontal``; render it as a checkbox multi-select whose
    # choices are the project's registered admin apps. Replaces the old per-model
    # ``user_permissions`` widget.
    admin_apps = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Admin apps"),
        help_text=_("Apps this member may manage. Superusers (I2G Master) ignore this list."),
    )

    # Declared explicitly (rather than via ``Meta.widgets``) so the field class — and therefore
    # ``has_changed`` and the upload validation — applies. See Base64ImageField.
    profile_image = Base64ImageField(
        required=False,
        label=_("Profile Image"),
        help_text=_("JPEG, PNG, GIF or WebP, 5 MB maximum. Larger images are scaled down to 512px."),
        widget=Base64ImageWidget(attrs={"accept": ",".join(ALLOWED_CONTENT_TYPES)}),
    )

    class Meta(UserChangeForm.Meta):
        model = Member
        fields = "__all__"
        # "Account active" rather than the inherited "Active", so it is not read as a flag of an address. Meta (not
        # the model) also labels the read-only display, and needs no migration.
        labels = MEMBER_LABELS
        help_texts = MEMBER_HELP_TEXTS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ``admin_apps`` is absent for non-superusers (the admin marks it
        # read-only so they can't self-grant app access), so only populate the
        # choices when the field is actually editable on this form.
        if "admin_apps" in self.fields:
            self.fields["admin_apps"].choices = admin_app_choices()
        if "profile_image" in self.fields and self.instance.pk and self.instance.profile_image:
            # The widget renders an <img> pointing here instead of inlining the stored base64.
            try:
                self.fields["profile_image"].widget.preview_url = reverse(
                    "admin:authn_member_profile_image", args=[self.instance.pk]
                )
            except NoReverseMatch:  # pragma: no cover - admin always mounted in this project
                self.fields["profile_image"].widget.preview_url = ""

    def clean_profile_image(self):
        """Keep the stored image unless the admin uploaded a new one or ticked "remove"."""
        value = self.cleaned_data.get("profile_image")
        if value == "":
            return ""
        if value is None and self.instance.pk:
            return self.instance.profile_image
        return value

"""
Admin forms for authn app.
"""

from django.contrib.auth.forms import SetPasswordMixin
from django.core.exceptions import ValidationError
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from unfold.forms import UserChangeForm, UserCreationForm

from ....models import Member
from ....services.members.accounts.profile_image import ALLOWED_CONTENT_TYPES
from ....services.members.admins import DEACTIVATE, DEMOTE, admin_removal_refusal
from ..shared.help_texts import MEMBER_HELP_TEXTS, MEMBER_LABELS
from .profile_image import Base64ImageField, Base64ImageWidget


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
    """User change form for the Member model with Unfold-styled password widget.

    Unticking **Admin** or **Account active** on an Admin account is refused (an error on that field) when it would
    remove the submitter's own Admin account or the last active Admin (``admin_removal_refusal``).
    """

    # The member submitting the form; ``MemberAdmin.get_form`` sets it per request. ``None`` (a form built outside
    # the admin) still keeps the last active Admin.
    removal_actor = None

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
        if "profile_image" in self.fields and self.instance.pk and self.instance.profile_image:
            # The widget renders an <img> pointing here instead of inlining the stored base64.
            try:
                self.fields["profile_image"].widget.preview_url = reverse(
                    "admin:authn_member_profile_image", args=[self.instance.pk]
                )
            except NoReverseMatch:  # pragma: no cover - admin always mounted in this project
                self.fields["profile_image"].widget.preview_url = ""

    def clean(self):
        cleaned_data = super().clean()
        member = self.instance
        if member._state.adding:  # nothing is stored yet, so nothing can be removed
            return cleaned_data
        # ``self.instance`` still holds the stored flags here: the form's values are copied onto it after clean().
        for field, action in (("is_staff", DEMOTE), ("is_active", DEACTIVATE)):
            if field in self.fields and field in cleaned_data and not cleaned_data[field] and getattr(member, field):
                refusal = admin_removal_refusal(self.removal_actor, [member], action=action)
                if refusal:
                    self.add_error(field, refusal)
        return cleaned_data

    def clean_profile_image(self):
        """Keep the stored image unless the admin uploaded a new one or ticked "remove"."""
        value = self.cleaned_data.get("profile_image")
        if value == "":
            return ""
        if value is None and self.instance.pk:
            return self.instance.profile_image
        return value

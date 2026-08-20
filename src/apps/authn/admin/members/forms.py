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

from ...models import Member
from ...services.members.profile_image import ALLOWED_CONTENT_TYPES, ProfileImageError, encode_profile_image


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


class Base64ImageWidget(forms.ClearableFileInput):
    """File upload widget for the base64 ``data:`` URI stored in ``Member.profile_image``.

    The preview is rendered from ``preview_url`` (an admin view that streams the decoded bytes), never
    by inlining the stored string. Inlining it put the whole value — up to ~6.8 MB — into one
    ``<img src>`` in the middle of the "Personal Info" fieldset, so on a slow or truncated response
    everything after it (the remaining fieldsets, both contact inlines and the only Save button) never
    arrived and the page looked read-only. The rendered markup is now a constant size for every member.
    """

    template_name = "admin/authn/member/widgets/base64_image.html"
    # i2g-admin-file-input: see admin/css/file-input.css (WebKit file button styling).
    _file_classes = "i2g-admin-file-input block w-full text-sm text-font-default-light dark:text-font-default-dark"

    def __init__(self, attrs=None):
        defaults = {"class": self._file_classes}
        if attrs:
            defaults.update(attrs)
        super().__init__(attrs=defaults)
        # Set per bound form by MemberChangeForm.__init__; the widget is deep-copied with the field,
        # so this stays request-scoped.
        self.preview_url = ""

    def value_from_datadict(self, data, files, name):
        """Return the upload, ``""`` to clear, or ``None`` for "keep the current image".

        The upload object is returned as-is rather than base64-encoded here: encoding needs to raise
        ``ValidationError`` (see ``Base64ImageField.to_python``), and reading the stream in a widget
        breaks any later reader. ``ConfirmOnSaveMixin`` caches ``request.FILES`` *after* the form has
        validated, so a widget that consumed the stream made it cache zero bytes and the confirmed
        save then overwrote the member's real image with an empty ``data:`` URI.
        """
        upload = files.get(name)
        if upload:
            return upload
        if self.clear_checkbox_name(name) in data:
            return ""
        return None  # No change

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def format_value(self, value):
        # Never let the stored base64 string reach the template context.
        return None

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        has_image = bool(value) and isinstance(value, str)
        context["widget"].update(
            {
                "value": None,
                "is_initial": has_image,
                "preview_url": self.preview_url if has_image else "",
            }
        )
        return context


class Base64ImageField(forms.CharField):
    """Form field for the base64 ``data:`` URI stored in ``Member.profile_image``.

    ``profile_image`` is a ``TextField``, so ``fields = "__all__"`` would give it a plain ``CharField``
    whose ``has_changed`` coerces the widget's "no change" ``None`` to ``""`` — making
    ``"data:image/png;base64,…" != ""`` true on every save. Every member save therefore logged
    "Changed Profile Image" and produced a phantom confirm-on-save diff row. ``FileField.has_changed``
    has the rule this needs (``data is not None``); mirror it here, and do the validation/encoding in
    ``to_python`` where a ``ValidationError`` can reach the user.
    """

    widget = Base64ImageWidget

    def to_python(self, value):
        if value is None or value == "":
            return value
        if hasattr(value, "read"):
            try:
                return encode_profile_image(value)
            except ProfileImageError as exc:
                raise ValidationError(str(exc), code="invalid_image") from exc
        # Already-encoded string (programmatic use and existing tests).
        return super().to_python(value)

    def has_changed(self, initial, data):
        if data is None:
            return False  # No file chosen and the clear checkbox was not ticked.
        if data == "":
            return bool(initial)  # Clearing only changes anything if there was an image.
        return True  # A file was chosen.


class MemberCreationForm(UserCreationForm):
    """User creation form for the Member model with Unfold-styled password widgets.

    Passwords are optional: leave both blank to create the member with an unusable password
    (set a password later or use other auth). If either field is set, both must match.
    """

    class Meta(UserCreationForm.Meta):
        model = Member
        fields = ()

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


class MemberImportForm(forms.Form):
    """Form for importing members from Excel file."""

    _input_classes = (
        "w-full border border-base-200 dark:border-base-700 bg-white dark:bg-base-900"
        " text-font-default-light dark:text-font-default-dark rounded-default px-3 py-2 text-sm"
    )
    _file_classes = "i2g-admin-file-input block w-full text-sm text-font-default-light dark:text-font-default-dark"

    excel_file = forms.FileField(
        label="Excel File",
        help_text="Upload a .xlsx or .xls format Excel file",
        widget=forms.FileInput(
            attrs={
                "accept": ".xlsx,.xls",
                "class": _file_classes,
            }
        ),
    )

    set_password = forms.CharField(
        label="Default Password",
        required=False,
        help_text="Set a default password for imported users (leave empty to generate random passwords)",
        widget=forms.PasswordInput(
            attrs={
                "class": _input_classes,
                "autocomplete": "new-password",
            }
        ),
    )

    update_existing = forms.BooleanField(
        label="Update Existing Members",
        required=False,
        initial=False,
        help_text="If a member with the same primary email already exists, update their info instead of skipping",
    )

    def clean_excel_file(self):
        """Validate the uploaded file."""
        file = self.cleaned_data.get("excel_file")
        if file:
            # Check file extension
            if not file.name.endswith((".xlsx", ".xls")):
                raise forms.ValidationError("Please upload a .xlsx or .xls format file")

            # Check file size (max 5MB)
            if file.size > 5 * 1024 * 1024:
                raise forms.ValidationError("File size cannot exceed 5MB")

        return file

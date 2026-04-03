"""
Admin forms for authn app.
"""

from django import forms
from unfold.forms import UserChangeForm, UserCreationForm

from ...models import Member


class Base64ImageWidget(forms.ClearableFileInput):
    """File upload widget that stores the image as a base64-encoded string in a TextField."""

    # i2g-admin-file-input: see admin/css/file-input.css (WebKit file button styling).
    _file_classes = (
        "i2g-admin-file-input block w-full text-sm text-font-default-light dark:text-font-default-dark"
    )

    def __init__(self, attrs=None):
        defaults = {"class": self._file_classes}
        if attrs:
            defaults.update(attrs)
        super().__init__(attrs=defaults)

    def value_from_datadict(self, data, files, name):
        upload = files.get(name)
        if upload:
            import base64

            return base64.b64encode(upload.read()).decode("utf-8")
        # Check if the clear checkbox was checked
        checkbox_name = self.clear_checkbox_name(name)
        if checkbox_name in data:
            return ""
        return None  # No change

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def format_value(self, value):
        # Return None so the default ClearableFileInput doesn't try to treat
        # the base64 string as a FieldFile object.
        return None

    def render(self, name, value, attrs=None, renderer=None):
        from django.utils.html import format_html
        from django.utils.safestring import mark_safe

        widget_html = super().render(name, None, attrs, renderer)
        # If there's existing base64 data, show a thumbnail preview above the upload control
        if value and isinstance(value, str) and len(value) > 50:
            preview = format_html(
                '<div class="mb-3 flex items-center gap-4">'
                '<img src="data:image/png;base64,{}" alt="Profile preview"'
                ' class="rounded-default border border-base-200 dark:border-base-700 object-cover"'
                ' style="width:80px;height:80px" />'
                '<span class="text-xs text-font-subtle-light dark:text-font-subtle-dark">Current image</span>'
                "</div>",
                value,
            )
            return mark_safe(preview + widget_html)
        return widget_html


class MemberCreationForm(UserCreationForm):
    """User creation form for the Member model with Unfold-styled password widgets."""

    class Meta(UserCreationForm.Meta):
        model = Member
        fields = ()


class MemberChangeForm(UserChangeForm):
    """User change form for the Member model with Unfold-styled password widget."""

    class Meta(UserChangeForm.Meta):
        model = Member
        fields = "__all__"
        widgets = {
            "profile_image": Base64ImageWidget(attrs={"accept": "image/png,image/jpeg"}),
        }

    def clean_profile_image(self):
        value = self.cleaned_data.get("profile_image")
        if value is None and self.instance.pk:
            return self.instance.profile_image
        return value


class MemberImportForm(forms.Form):
    """Form for importing members from Excel file."""

    _input_classes = (
        "w-full border border-base-200 dark:border-base-700 bg-white dark:bg-base-900"
        " text-font-default-light dark:text-font-default-dark rounded-default px-3 py-2 text-sm"
    )
    _file_classes = (
        "i2g-admin-file-input block w-full text-sm text-font-default-light dark:text-font-default-dark"
    )

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

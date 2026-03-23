"""
Admin forms for authn app.
"""

from django import forms
from unfold.forms import UserChangeForm, UserCreationForm

from ...models import Member


class MemberCreationForm(UserCreationForm):
    """User creation form for the Member model with Unfold-styled password widgets."""

    class Meta(UserCreationForm.Meta):
        model = Member
        fields = ("username", "email")


class MemberChangeForm(UserChangeForm):
    """User change form for the Member model with Unfold-styled password widget."""

    class Meta(UserChangeForm.Meta):
        model = Member
        fields = "__all__"


class Base64ImageWidget(forms.ClearableFileInput):
    """File upload widget that stores the image as a base64-encoded string in a TextField."""

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
                '<div style="margin-bottom:8px">'
                '<p class="text-xs text-font-subtle-light dark:text-font-subtle-dark mb-1">Current image:</p>'
                '<img src="data:image/png;base64,{}" alt="Profile preview"'
                ' style="max-width:96px;max-height:96px;border-radius:6px;'
                'border:1px solid #e5e7eb;object-fit:cover"'
                " />"
                "</div>",
                value,
            )
            return mark_safe(preview + widget_html)
        return widget_html


class MemberProfileInlineForm(forms.ModelForm):
    """Form for MemberProfile inline that uses a file upload for the base64 profile_image field."""

    class Meta:
        from ...models import MemberProfile

        model = MemberProfile
        fields = "__all__"
        widgets = {
            "profile_image": Base64ImageWidget(attrs={"accept": "image/png,image/jpeg"}),
        }


class MemberImportForm(forms.Form):
    """Form for importing members from Excel file."""

    _input_classes = (
        "w-full border border-base-200 dark:border-base-700 bg-white dark:bg-base-900"
        " text-font-default-light dark:text-font-default-dark rounded-default px-3 py-2 text-sm"
    )
    _file_classes = (
        "block w-full text-sm text-font-default-light dark:text-font-default-dark"
        " file:mr-4 file:py-2 file:px-4 file:rounded-default file:border file:border-base-200"
        " file:dark:border-base-700 file:text-sm file:font-medium file:bg-base-50"
        " file:dark:bg-base-800 file:text-font-default-light file:dark:text-font-default-dark"
        " hover:file:bg-base-100 dark:hover:file:bg-base-700 file:cursor-pointer file:transition-colors"
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

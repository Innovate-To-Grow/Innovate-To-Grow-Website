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

    def format_value(self, value):
        # Return None so the widget shows "No file currently" or similar
        return None


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

    excel_file = forms.FileField(
        label="Excel File",
        help_text="Upload a .xlsx or .xls format Excel file",
        widget=forms.FileInput(
            attrs={
                "accept": ".xlsx,.xls",
                "class": "vTextField",
            }
        ),
    )

    set_password = forms.CharField(
        label="Default Password",
        required=False,
        help_text="Set a default password for imported users (leave empty to generate random passwords)",
        widget=forms.PasswordInput(
            attrs={
                "class": "vTextField",
                "autocomplete": "new-password",
            }
        ),
    )

    send_welcome_email = forms.BooleanField(
        label="Send Welcome Email",
        required=False,
        initial=False,
        help_text="Send welcome email to users after import (requires email service configuration)",
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

"""Forms for the Notification Delivery settings page."""

from django import forms
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, SMTPProviderConfig


class EmailDeliveryForm(forms.ModelForm):
    class Meta:
        model = EmailServiceConfig
        fields = (
            "name",
            "is_active",
            "provider",
            "from_name",
            "from_email",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_admin_widget_classes(self)


class AwsDeliveryForm(forms.ModelForm):
    class Meta:
        model = AWSCredentialConfig
        fields = (
            "name",
            "is_active",
            "access_key_id",
            "secret_access_key",
            "default_region",
            "sms_message_template",
        )
        widgets = {
            "secret_access_key": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_admin_widget_classes(self)


class KeepWhenBlankField(forms.CharField):
    """A secret input that is never rendered back: left blank, it keeps the stored value, which is not a change."""

    def has_changed(self, initial, data):
        return bool(data) and super().has_changed(initial, data)


class SMTPDeliveryForm(forms.ModelForm):
    class Meta:
        model = SMTPProviderConfig
        fields = ("name", "is_active", "host", "port", "username", "password", "use_tls", "use_ssl", "timeout")
        field_classes = {"password": KeepWhenBlankField}
        widgets = {"password": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=False)}

    def __init__(self, *args, enabled=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].required = False
        self.fields["password"].help_text = "Leave blank to keep the existing password."
        for field in self.fields.values():
            field.widget.attrs["data-smtp-required"] = "true" if field.required else "false"
            field.disabled = not enabled
        _apply_admin_widget_classes(self)

    def clean_password(self):
        return self.cleaned_data["password"] or self.instance.password


def _apply_admin_widget_classes(form):
    input_class = "w-full rounded-md border border-base-300 px-3 py-2 text-sm"
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.setdefault("class", "rounded border-base-300")
            continue
        existing = field.widget.attrs.get("class", "")
        field.widget.attrs["class"] = f"{existing} {input_class}".strip()

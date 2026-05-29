"""Campaign admin widgets."""

from django import forms
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget


class PersonalizationTextInput(UnfoldAdminTextInputWidget):
    """Unfold text input with clickable personalization tag buttons."""

    template_name = "admin/mail/widgets/personalization_input.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["tags"] = [
            ("{{first_name}}", "First Name"),
            ("{{last_name}}", "Last Name"),
            ("{{full_name}}", "Full Name"),
            ("{{login_link}}", "Login Link"),
        ]
        return context


class ManualEmailsWidget(forms.Textarea):
    """Textarea with email count, validation hints, and paste support."""

    template_name = "admin/mail/widgets/manual_emails.html"

    def __init__(self, attrs=None):
        defaults = {"rows": 6, "placeholder": "one@example.com\ntwo@example.com\nthree@example.com"}
        if attrs:
            defaults.update(attrs)
        super().__init__(attrs=defaults)


class TicketSelectWidget(UnfoldAdminSelectWidget):
    """Select widget that carries data-event on each option for JS filtering."""

    template_name = "admin/mail/widgets/ticket_select.html"

    def _get_event_map(self):
        try:
            return {str(pk): str(eid) for pk, eid in self.choices.queryset.values_list("pk", "event_id")}
        except AttributeError:
            return {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value:
            if not hasattr(self, "_event_map"):
                self._event_map = self._get_event_map()
            event_id = self._event_map.get(str(value))
            if event_id:
                option["attrs"]["data-event"] = event_id
        return option


BODY_FORMAT_CHOICES = [("plain", "Plain Text"), ("html", "HTML")]

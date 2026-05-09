"""Campaign admin forms."""

from django import forms
from unfold.widgets import (
    UnfoldAdminRadioSelectWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextareaWidget,
)

from event.models import Ticket
from mail.login_redirects import DEFAULT_LOGIN_REDIRECT_PATH, get_login_redirect_choices
from mail.models import EmailCampaign
from mail.models.campaign import ALL_AUDIENCE_CHOICES, EXCLUDE_AUDIENCE_CHOICES
from mail.services.preview import HTML_MARKER

from .widgets import BODY_FORMAT_CHOICES, ManualEmailsWidget, PersonalizationTextInput, TicketSelectWidget


class EmailCampaignForm(forms.ModelForm):
    ticket = forms.ModelChoiceField(
        queryset=Ticket.objects.select_related("event").order_by("event__name", "order", "name"),
        required=False,
        label="Ticket type",
        widget=TicketSelectWidget,
    )
    exclude_ticket = forms.ModelChoiceField(
        queryset=Ticket.objects.select_related("event").order_by("event__name", "order", "name"),
        required=False,
        label="Exclude ticket type",
        widget=TicketSelectWidget,
    )
    body_format = forms.ChoiceField(
        choices=BODY_FORMAT_CHOICES,
        initial="plain",
        required=False,
        label="Email format",
        widget=UnfoldAdminRadioSelectWidget,
    )
    login_redirect_path = forms.ChoiceField(
        choices=(),
        initial=DEFAULT_LOGIN_REDIRECT_PATH,
        label="Post-login destination",
        help_text="Choose the internal page recipients should see after using {{login_link}}.",
        widget=UnfoldAdminSelectWidget,
    )

    class Meta:
        model = EmailCampaign
        fields = "__all__"
        widgets = {
            "subject": PersonalizationTextInput,
            "manual_emails": ManualEmailsWidget,
            "body": UnfoldAdminTextareaWidget,
            "audience_type": UnfoldAdminSelectWidget,
            "event": UnfoldAdminSelectWidget,
            "member_email_scope": UnfoldAdminSelectWidget,
            "exclude_audience_type": UnfoldAdminSelectWidget,
            "exclude_event": UnfoldAdminSelectWidget,
            "exclude_member_email_scope": UnfoldAdminSelectWidget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "audience_type" in self.fields:
            self.fields["audience_type"].choices = ALL_AUDIENCE_CHOICES
        if "exclude_audience_type" in self.fields:
            self.fields["exclude_audience_type"].choices = EXCLUDE_AUDIENCE_CHOICES
        self.fields.pop("exclude_ticket_id", None)

        current_path = self.initial.get("login_redirect_path") or getattr(self.instance, "login_redirect_path", None)
        if "login_redirect_path" in self.fields:
            self.fields["login_redirect_path"].choices = get_login_redirect_choices(current_path=current_path)

        if self.instance and self.instance.pk and self.instance.status != "draft":
            self._disable_sent_campaign_fields()

        if self.instance and self.instance.pk and self.instance.audience_type == "ticket_type":
            self._restore_ticket_initial()
        if self.instance and self.instance.pk and self.instance.exclude_audience_type == "ticket_type":
            self._restore_exclude_ticket_initial()

        body_val = self.initial.get("body") or (self.instance.body if self.instance and self.instance.pk else "")
        if body_val.startswith(HTML_MARKER):
            self.initial["body_format"] = "html"
            self.initial["body"] = body_val[len(HTML_MARKER) :]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("audience_type") == "ticket_type":
            self._clean_ticket_type(cleaned)

        exclude_type = (cleaned.get("exclude_audience_type") or "").strip()
        if exclude_type == "ticket_type":
            self._clean_exclude_ticket_type(cleaned)
        else:
            cleaned["exclude_ticket_id"] = ""
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.audience_type == "ticket_type":
            ticket = self.cleaned_data.get("ticket")
            if ticket:
                instance.manual_emails = str(ticket.pk)

        exclude_type = (instance.exclude_audience_type or "").strip()
        if not exclude_type:
            instance.exclude_event_id = None
            instance.exclude_ticket_id = ""
        else:
            instance.exclude_ticket_id = (self.cleaned_data.get("exclude_ticket_id") or "").strip()

        if self.cleaned_data.get("body_format") == "html" and not instance.body.startswith(HTML_MARKER):
            instance.body = HTML_MARKER + instance.body

        if commit:
            instance.save()
            self.save_m2m()
        return instance

    def _disable_sent_campaign_fields(self):
        for field_name in (
            "subject",
            "login_redirect_path",
            "include_unsubscribe_header",
            "body_format",
            "body",
            "audience_type",
            "event",
            "ticket",
            "selected_members",
            "member_email_scope",
            "manual_emails",
            "exclude_audience_type",
            "exclude_event",
            "exclude_ticket",
            "exclude_members",
            "exclude_member_email_scope",
        ):
            if field_name in self.fields:
                self.fields[field_name].disabled = True

    def _restore_ticket_initial(self):
        ticket_id = self.instance.manual_emails.strip()
        if ticket_id:
            try:
                self.initial["ticket"] = Ticket.objects.get(pk=ticket_id).pk
            except Ticket.DoesNotExist:
                pass

    def _restore_exclude_ticket_initial(self):
        ticket_id = self.instance.exclude_ticket_id.strip()
        if ticket_id:
            try:
                self.initial["exclude_ticket"] = Ticket.objects.get(pk=ticket_id).pk
            except Ticket.DoesNotExist:
                pass

    def _clean_ticket_type(self, cleaned):
        ticket = cleaned.get("ticket")
        if not ticket:
            self.add_error("ticket", "A ticket type must be selected.")
            return
        event = cleaned.get("event")
        if event and ticket.event_id != event.pk:
            self.add_error("ticket", "Selected ticket does not belong to the selected event.")
        cleaned["manual_emails"] = str(ticket.pk)

    def _clean_exclude_ticket_type(self, cleaned):
        exclude_ticket = cleaned.get("exclude_ticket")
        if not exclude_ticket:
            self.add_error("exclude_ticket", "A ticket type must be selected for ticket exclusion.")
            return
        exclude_event = cleaned.get("exclude_event")
        if exclude_event and exclude_ticket.event_id != exclude_event.pk:
            self.add_error("exclude_ticket", "Selected ticket does not belong to the exclusion event.")
        cleaned["exclude_ticket_id"] = str(exclude_ticket.pk)

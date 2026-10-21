"""The SMS campaign admin form: audience, ticket filters and the send-locked fields."""

from django import forms
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget

from apps.event.models import Ticket
from apps.mail.admin.campaign.widgets import TicketSelectWidget
from apps.mail.models import SmsCampaign
from apps.mail.models.sms_campaign import SMS_AUDIENCE_CHOICES, SMS_EXCLUDE_AUDIENCE_CHOICES


class SmsCampaignForm(forms.ModelForm):
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

    class Meta:
        model = SmsCampaign
        fields = "__all__"
        widgets = {
            "name": forms.TextInput,
            "message": UnfoldAdminTextareaWidget,
            "phone_policy": UnfoldAdminSelectWidget,
            "audience_type": UnfoldAdminSelectWidget,
            "event": UnfoldAdminSelectWidget,
            "ticket_id": forms.HiddenInput,
            "manual_phones": UnfoldAdminTextareaWidget,
            "exclude_audience_type": UnfoldAdminSelectWidget,
            "exclude_event": UnfoldAdminSelectWidget,
            "exclude_ticket_id": forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "audience_type" in self.fields:
            self.fields["audience_type"].choices = SMS_AUDIENCE_CHOICES
        if "exclude_audience_type" in self.fields:
            self.fields["exclude_audience_type"].choices = SMS_EXCLUDE_AUDIENCE_CHOICES

        if self.instance and self.instance.pk and self.instance.status != "draft":
            self._disable_sent_campaign_fields()
        if self.instance and self.instance.pk and self.instance.audience_type == "ticket_type":
            self._restore_ticket_initial()
        if self.instance and self.instance.pk and self.instance.exclude_audience_type == "ticket_type":
            self._restore_exclude_ticket_initial()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("audience_type") == "ticket_type":
            self._clean_ticket_type(cleaned)
        else:
            cleaned["ticket_id"] = ""

        exclude_type = (cleaned.get("exclude_audience_type") or "").strip()
        if exclude_type == "ticket_type":
            self._clean_exclude_ticket_type(cleaned)
        else:
            cleaned["exclude_ticket_id"] = ""
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.audience_type != "ticket_type":
            instance.ticket_id = ""
        if not (instance.exclude_audience_type or "").strip():
            instance.exclude_event_id = None
            instance.exclude_ticket_id = ""
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    def _disable_sent_campaign_fields(self):
        for field_name in (
            "name",
            "message",
            "phone_policy",
            "audience_type",
            "event",
            "ticket",
            "ticket_id",
            "selected_members",
            "manual_phones",
            "exclude_audience_type",
            "exclude_event",
            "exclude_ticket",
            "exclude_ticket_id",
            "exclude_members",
        ):
            if field_name in self.fields:
                self.fields[field_name].disabled = True

    def _restore_ticket_initial(self):
        ticket_id = self.instance.ticket_id.strip()
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
        cleaned["ticket_id"] = str(ticket.pk)

    def _clean_exclude_ticket_type(self, cleaned):
        exclude_ticket = cleaned.get("exclude_ticket")
        if not exclude_ticket:
            self.add_error("exclude_ticket", "A ticket type must be selected for ticket exclusion.")
            return
        exclude_event = cleaned.get("exclude_event")
        if exclude_event and exclude_ticket.event_id != exclude_event.pk:
            self.add_error("exclude_ticket", "Selected ticket does not belong to the exclusion event.")
        cleaned["exclude_ticket_id"] = str(exclude_ticket.pk)

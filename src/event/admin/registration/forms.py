from django import forms

from ...models import EventRegistration, Ticket


class EventRegistrationAdminForm(forms.ModelForm):
    send_ticket_email = forms.BooleanField(
        required=False,
        initial=False,
        label="Send ticket email to attendee",
        help_text=("If checked, a confirmation email with the ticket barcode will be sent " "after saving."),
    )

    class Meta:
        model = EventRegistration
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.event_id and "ticket" in self.fields:
            self.fields["ticket"].queryset = Ticket.objects.filter(event=self.instance.event).order_by(
                "order",
                "name",
            )

    def clean(self):
        cleaned = super().clean()
        event = cleaned.get("event") or getattr(self.instance, "event", None)
        ticket = cleaned.get("ticket")
        member = cleaned.get("member") or getattr(self.instance, "member", None)

        if event and ticket and ticket.event_id != event.pk:
            raise forms.ValidationError({"ticket": "This ticket does not belong to the selected event."})

        if member and event and not self.instance.pk:
            duplicate = EventRegistration.objects.filter(member=member, event=event).exists()
            if duplicate:
                raise forms.ValidationError({"member": ("This member is already registered for the selected event.")})

        return cleaned

    def clean_question_answers(self):
        answers = self.cleaned_data.get("question_answers")
        if answers in (None, ""):
            return []
        if not isinstance(answers, list):
            raise forms.ValidationError("Question answers must be a JSON list.")
        return answers

    def clean_attendee_phone(self):
        phone = self.cleaned_data.get("attendee_phone", "").strip()
        if not phone:
            return phone
        from event.views.registration import _validate_phone_digits

        error = _validate_phone_digits(phone, "0-GENERIC")
        if error:
            raise forms.ValidationError(error)
        return phone

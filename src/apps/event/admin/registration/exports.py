from .config import EXPORT_FIELDS


class RegistrationExportMixin:
    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("event", "ticket", "member")
            .prefetch_related("member__contact_emails", "member__contact_phones")
        )

    def get_export_fields(self):
        return list(EXPORT_FIELDS)

    def _resolve_columns(self, request):
        """Accept the former Event Date key without showing it in new exports."""
        selected = request.POST.getlist("export_fields")
        all_fields = {**dict(self.get_export_fields()), "event_date": "Event Date"}
        columns = [(name, all_fields[name]) for name in selected if name in all_fields]
        return columns or list(self.get_export_fields())

    def get_export_value(self, obj, field_name):
        getter = _REGISTRATION_EXPORT_VALUES.get(field_name)
        if getter is not None:
            return getter(self, obj)
        return super().get_export_value(obj, field_name)

    # noinspection PyMethodMayBeStatic
    def _member_emails(self, member, email_type):
        contacts = member.contact_emails.all()
        return "; ".join(
            contact.email_address
            for contact in sorted(contacts, key=lambda contact: contact.created_at)
            if contact.email_type == email_type
        )

    # noinspection PyMethodMayBeStatic
    def _member_phone_numbers(self, member):
        phones = sorted(
            member.contact_phones.all(),
            key=lambda phone: (not phone.verified, phone.created_at),
        )
        return "; ".join(phone.get_formatted_number() for phone in phones)


# Computed export columns: field name -> (admin, registration) -> value. Other fields
# fall back to the model attribute.
_REGISTRATION_EXPORT_VALUES = {
    "event_name": lambda admin, obj: obj.event.name,
    "event_slug": lambda admin, obj: obj.event.slug,
    "event_date": lambda admin, obj: obj.event.date,
    "event_start_date": lambda admin, obj: obj.event.date,
    "event_end_date": lambda admin, obj: obj.event.effective_end_date,
    "ticket_name": lambda admin, obj: obj.ticket.name,
    "attendee_name": lambda admin, obj: obj.attendee_name,
    "member_id": lambda admin, obj: str(obj.member.pk),
    "member_full_name": lambda admin, obj: obj.member.get_full_name(),
    "member_first_name": lambda admin, obj: obj.member.first_name,
    "member_middle_name": lambda admin, obj: obj.member.middle_name or "",
    "member_last_name": lambda admin, obj: obj.member.last_name,
    "member_title": lambda admin, obj: obj.member.title or "",
    "member_organization": lambda admin, obj: obj.member.organization or "",
    "member_primary_email": lambda admin, obj: admin._member_emails(obj.member, "primary"),
    "member_secondary_emails": lambda admin, obj: admin._member_emails(obj.member, "secondary"),
    "member_other_emails": lambda admin, obj: admin._member_emails(obj.member, "other"),
    "member_phone_numbers": lambda admin, obj: admin._member_phone_numbers(obj.member),
}

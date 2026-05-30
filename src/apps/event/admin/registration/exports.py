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

    def get_export_value(self, obj, field_name):
        member = obj.member
        if field_name == "event_name":
            return obj.event.name
        if field_name == "event_slug":
            return obj.event.slug
        if field_name == "event_date":
            return obj.event.date
        if field_name == "ticket_name":
            return obj.ticket.name
        if field_name == "attendee_name":
            return obj.attendee_name
        if field_name == "member_id":
            return str(member.pk)
        if field_name == "member_full_name":
            return member.get_full_name()
        if field_name == "member_first_name":
            return member.first_name
        if field_name == "member_middle_name":
            return member.middle_name or ""
        if field_name == "member_last_name":
            return member.last_name
        if field_name == "member_title":
            return member.title or ""
        if field_name == "member_organization":
            return member.organization or ""
        if field_name == "member_primary_email":
            return self._member_emails(member, "primary")
        if field_name == "member_secondary_emails":
            return self._member_emails(member, "secondary")
        if field_name == "member_other_emails":
            return self._member_emails(member, "other")
        if field_name == "member_phone_numbers":
            return self._member_phone_numbers(member)
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

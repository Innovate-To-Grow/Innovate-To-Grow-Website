from django.db.models import Count
from django.http import JsonResponse

from ...models import Event


class RegistrationInfoViewsMixin:
    # noinspection PyMethodMayBeStatic
    def _member_info_view(self, request, pk):
        from authn.models import Member

        try:
            member = Member.objects.get(pk=pk)
        except Member.DoesNotExist:
            return JsonResponse({"error": "Not found"}, status=404)

        emails = list(
            member.contact_emails.order_by("email_type", "created_at").values_list("email_address", flat=True)
        )
        phones = [
            contact_phone.get_formatted_number()
            for contact_phone in member.contact_phones.order_by("-verified", "created_at")
        ]
        return JsonResponse(
            {
                "name": member.get_full_name(),
                "emails": emails,
                "phones": phones,
                "organization": member.organization or "",
                "title": member.title or "",
            }
        )

    # noinspection PyMethodMayBeStatic
    def _event_info_view(self, request, pk):
        try:
            event = Event.objects.prefetch_related("tickets", "questions").get(pk=pk)
        except Event.DoesNotExist:
            return JsonResponse({"error": "Not found"}, status=404)

        ticket_data = (
            event.tickets.annotate(reg_count=Count("registrations"))
            .order_by("order", "name")
            .values("name", "reg_count")
        )
        tickets = [{"name": ticket["name"], "registrations": ticket["reg_count"]} for ticket in ticket_data]
        total_registrations = sum(ticket["reg_count"] for ticket in ticket_data)

        questions = [
            {"text": question.text, "required": question.is_required} for question in event.questions.order_by("order")
        ]

        return JsonResponse(
            {
                "name": event.name,
                "slug": event.slug,
                "date": event.date.isoformat(),
                "location": event.location,
                "description": event.description,
                "is_live": event.is_live,
                "allow_secondary_email": event.allow_secondary_email,
                "collect_phone": event.collect_phone,
                "verify_phone": event.verify_phone,
                "total_registrations": total_registrations,
                "tickets": tickets,
                "questions": questions,
            }
        )

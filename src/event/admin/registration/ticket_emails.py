import logging

from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse

from ...models import EventRegistration

logger = logging.getLogger(__name__)


class TicketEmailAdminMixin:
    @admin.action(description="Resend ticket email")
    def resend_ticket_email(self, request, queryset):
        self._send_ticket_email_batch(request, queryset)

    def _send_ticket_email_batch(self, request, queryset):
        from event.services.ticket_mail import send_ticket_email

        sent = 0
        for registration in queryset.select_related("event", "ticket", "member"):
            try:
                send_ticket_email(registration)
                sent += 1
            except Exception:
                logger.exception("Failed to send ticket email for registration %s", registration.pk)
                messages.error(
                    request,
                    ("Failed to send email for " f"{registration.attendee_name or registration.ticket_code}."),
                )
        if sent:
            messages.success(request, f"Sent ticket email to {sent} registration(s).")
        return sent

    def send_all_ticket_emails_view(self, request):
        changelist_url = reverse("admin:event_eventregistration_changelist")
        queryset = EventRegistration.objects.select_related("event", "ticket", "member").order_by("created_at")
        registration_count = queryset.count()

        if request.method == "POST":
            if registration_count == 0:
                messages.warning(request, "No event registrations found.")
                return redirect(changelist_url)

            self._send_ticket_email_batch(request, queryset)
            return redirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "title": "Send Ticket Emails to All Registrants",
            "changelist_url": changelist_url,
            "registration_count": registration_count,
            "already_sent_count": queryset.exclude(ticket_email_sent_at__isnull=True).count(),
            "error_count": queryset.exclude(ticket_email_error="").count(),
        }
        return TemplateResponse(
            request,
            "admin/event/eventregistration/send_all_ticket_emails.html",
            context,
        )

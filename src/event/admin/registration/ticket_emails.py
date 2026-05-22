import logging

from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html

from ...models import EventRegistration

logger = logging.getLogger(__name__)


class TicketEmailAdminMixin:
    @admin.display(description="Ticket email")
    def send_ticket_email_action(self, obj):
        if not obj or not obj.pk:
            return "-"
        return format_html(
            '<div class="flex flex-col gap-2">'
            '<button type="submit" name="_send_ticket_email" value="1" '
            'class="bg-primary-600 border border-transparent cursor-pointer font-medium '
            'px-3 py-2 rounded-default text-white w-full lg:w-auto">'
            "Send ticket email now"
            "</button>"
            '<p class="text-xs text-base-500 dark:text-base-400">'
            "Saves the current ticket selection first, then sends the confirmation email."
            "</p>"
            "</div>"
        )

    @admin.action(description="Resend ticket email")
    def resend_ticket_email(self, request, queryset):
        self._send_ticket_email_batch(request, queryset)

    def _send_ticket_email_registration(self, request, registration, *, show_success=True):
        from event.services.ticket_mail import send_ticket_email

        try:
            send_ticket_email(registration)
        except Exception:
            logger.exception("Failed to send ticket email for registration %s", registration.pk)
            messages.error(
                request,
                ("Failed to send email for " f"{registration.attendee_name or registration.ticket_code}."),
            )
            return False

        if show_success:
            messages.success(
                request,
                f"Sent ticket email to {registration.attendee_name or registration.ticket_code}.",
            )
        return True

    def _send_ticket_email_batch(self, request, queryset):
        sent = 0
        for registration in queryset.select_related("event", "ticket", "member"):
            if self._send_ticket_email_registration(request, registration, show_success=False):
                sent += 1
        if sent:
            messages.success(request, f"Sent ticket email to {sent} registration(s).")
        return sent

    def send_all_ticket_emails_view(self, request):
        changelist_url = reverse("admin:event_eventregistration_changelist")
        queryset = EventRegistration.objects.select_related("event", "ticket", "member").order_by("created_at")
        registration_count = queryset.count()

        first_registration = queryset.first()
        event_name = first_registration.event.name if first_registration and first_registration.event else ""

        if request.method == "POST":
            if registration_count == 0:
                messages.warning(request, "No event registrations found.")
                return redirect(changelist_url)

            from django.conf import settings as django_settings

            if getattr(django_settings, "ADMIN_REQUIRE_CONFIRMATION", True):
                confirmation_text = request.POST.get("confirmation_text", "").strip()
                if not event_name or confirmation_text != event_name:
                    messages.error(request, "Confirmation text does not match event name. Please try again.")
                    return redirect(reverse("admin:event_eventregistration_send_all_ticket_emails"))

            sent = self._send_ticket_email_batch(request, queryset)

            from core.admin.notifications import notify_staff_of_action

            notify_staff_of_action(
                actor=request.user,
                action=f"Sent Ticket Emails: {event_name}",
                summary=[
                    {"label": "Event", "value": event_name},
                    {"label": "Total registrations", "value": str(registration_count)},
                    {"label": "Emails sent", "value": str(sent)},
                ],
                admin_url=request.build_absolute_uri(changelist_url),
            )

            return redirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "title": "Send Ticket Emails to All Registrants",
            "changelist_url": changelist_url,
            "registration_count": registration_count,
            "already_sent_count": queryset.exclude(ticket_email_sent_at__isnull=True).count(),
            "error_count": queryset.exclude(ticket_email_error="").count(),
            "event_name": event_name,
        }
        return TemplateResponse(
            request,
            "admin/event/eventregistration/send_all_ticket_emails.html",
            context,
        )

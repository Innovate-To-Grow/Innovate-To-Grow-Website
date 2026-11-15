from io import BytesIO
from unittest.mock import patch

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.test import override_settings
from django.urls import reverse
from openpyxl import load_workbook

from apps.authn.models import ContactEmail, ContactPhone
from apps.event.admin.registration import EventRegistrationAdmin
from apps.event.models import EventRegistration
from apps.event.tests.admin.registrations.test_registration_admin import _EventRegistrationAdminCase
from apps.event.tests.helpers import (
    make_event,
    make_member,
    make_registration,
    make_ticket,
)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class EventRegistrationAdminTest(_EventRegistrationAdminCase):
    def test_export_excel_includes_member_profile_and_contacts(self):
        event = make_event(name="Export Event")
        ticket = make_ticket(event, name="VIP")
        member = make_member(
            email="export-primary@example.com",
            first_name="Ada",
            middle_name="Byron",
            last_name="Lovelace",
            organization="Analytical Engines",
            title="Chief Scientist",
        )
        ContactEmail.objects.create(
            member=member,
            email_address="export-secondary@example.com",
            email_type="secondary",
            verified=True,
        )
        ContactEmail.objects.create(
            member=member,
            email_address="export-other@example.com",
            email_type="other",
            verified=False,
        )
        ContactPhone.objects.create(
            member=member,
            phone_number="2095551212",
            region="1-US",
            verified=True,
        )
        registration = make_registration(
            member,
            event,
            ticket,
            attendee_first_name="Grace",
            attendee_last_name="Hopper",
            attendee_email="grace@example.com",
            attendee_secondary_email="grace.secondary@example.com",
            attendee_phone="2095552323",
            attendee_organization="Navy",
        )

        response = self.client.post(
            "/admin/event/eventregistration/",
            {
                "action": "export_data",
                ACTION_CHECKBOX_NAME: str(registration.pk),
                "export_confirm": "1",
                "export_format": "xlsx",
                "export_filename": "registration_export",
                "export_fields": [
                    "event_name",
                    "ticket_name",
                    "attendee_email",
                    "attendee_organization",
                    "member_full_name",
                    "member_title",
                    "member_organization",
                    "member_primary_email",
                    "member_secondary_emails",
                    "member_other_emails",
                    "member_phone_numbers",
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        rows = list(workbook.active.iter_rows(values_only=True))
        self.assertEqual(
            rows[0],
            (
                "Event Name",
                "Ticket",
                "Attendee Email",
                "Attendee Organization",
                "Member Full Name",
                "Member Title",
                "Member Organization",
                "Member Primary Email",
                "Member Secondary Emails",
                "Member Other Emails",
                "Member Phone Numbers",
            ),
        )
        self.assertEqual(
            rows[1],
            (
                "Export Event",
                "VIP",
                "grace@example.com",
                "Navy",
                "Ada Byron Lovelace",
                "Chief Scientist",
                "Analytical Engines",
                "export-primary@example.com",
                "export-secondary@example.com",
                "export-other@example.com",
                "(209)555-1212",
            ),
        )

    def test_send_all_ticket_emails_confirmation_page(self):
        event = make_event()
        ticket = make_ticket(event)
        member = make_member(email="ticket-confirm@example.com")
        make_registration(member, event, ticket)

        response = self.client.get(reverse("admin:event_eventregistration_send_all_ticket_emails"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send Ticket Emails to All Registrants")
        self.assertContains(response, "You are about to send ticket emails to 1 registrant")

    @patch("apps.event.services.ticket.mail.send_ticket_email")
    def test_send_all_ticket_emails_posts_all_registrations(self, mock_send):
        event = make_event()
        ticket = make_ticket(event)
        member_one = make_member(email="ticket-one@example.com")
        member_two = make_member(email="ticket-two@example.com")
        registration_one = make_registration(member_one, event, ticket)
        registration_two = make_registration(member_two, event, ticket)

        response = self.client.post(reverse("admin:event_eventregistration_send_all_ticket_emails"))

        self.assertRedirects(response, reverse("admin:event_eventregistration_changelist"))
        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual(
            {call.args[0].pk for call in mock_send.call_args_list},
            {registration_one.pk, registration_two.pk},
        )

    @patch("apps.event.services.ticket.mail.send_ticket_email")
    def test_send_all_ticket_emails_empty_queryset_does_not_send(self, mock_send):
        response = self.client.post(reverse("admin:event_eventregistration_send_all_ticket_emails"))

        self.assertRedirects(response, reverse("admin:event_eventregistration_changelist"))
        mock_send.assert_not_called()

    def test_has_add_permission(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/admin/")
        request.user = self.admin_user
        admin_instance = EventRegistrationAdmin(EventRegistration, None)
        self.assertTrue(admin_instance.has_add_permission(request))

    def test_add_form_accessible(self):
        response = self.client.get("/admin/event/eventregistration/add/")
        self.assertEqual(response.status_code, 200)

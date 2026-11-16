from unittest.mock import patch

from django.test import override_settings

from apps.authn.models import ContactEmail, Member
from apps.event.admin.registration import EventRegistrationAdmin
from apps.event.models import EventRegistration, Ticket
from apps.event.tests.admin.registrations.test_registration_admin import _EventRegistrationAdminCase
from apps.event.tests.helpers import (
    make_event,
    make_member,
    make_registration,
    make_ticket,
)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class EventRegistrationAdminTest(_EventRegistrationAdminCase):
    @patch("apps.event.services.registration_sheet_sync.schedule_registration_sync")
    def test_admin_add_creates_registration(self, mock_sync):
        member = Member.objects.create_user(password="testpass123")
        ContactEmail.objects.create(
            member=member,
            email_address="reg@e.com",
            email_type="primary",
            verified=True,
        )
        event = make_event()
        ticket = Ticket.objects.create(event=event, name="GA")
        mock_sync.reset_mock()
        response = self.client.post(
            "/admin/event/eventregistration/add/",
            {
                "member": str(member.pk),
                "event": str(event.pk),
                "ticket": str(ticket.pk),
                "attendee_first_name": "",
                "attendee_last_name": "",
                "attendee_email": "",
                "attendee_secondary_email": "",
                "attendee_phone": "",
                "attendee_organization": "",
                "phone_verified": "",
                "question_answers": "[]",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EventRegistration.objects.filter(member=member, event=event).exists())
        mock_sync.assert_called_once_with(event)

    def test_admin_add_rejects_duplicate(self):
        member = Member.objects.create_user(password="testpass123")
        ContactEmail.objects.create(
            member=member,
            email_address="dup@e.com",
            email_type="primary",
            verified=True,
        )
        event = make_event()
        ticket = Ticket.objects.create(event=event, name="GA")
        EventRegistration.objects.create(member=member, event=event, ticket=ticket)
        response = self.client.post(
            "/admin/event/eventregistration/add/",
            {
                "member": str(member.pk),
                "event": str(event.pk),
                "ticket": str(ticket.pk),
                "attendee_first_name": "",
                "attendee_last_name": "",
                "attendee_email": "",
                "attendee_secondary_email": "",
                "attendee_phone": "",
                "attendee_organization": "",
                "phone_verified": "",
                "question_answers": "[]",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EventRegistration.objects.filter(member=member, event=event).count(), 1)

    def test_admin_add_rejects_mismatched_ticket(self):
        member = Member.objects.create_user(password="testpass123")
        ContactEmail.objects.create(
            member=member,
            email_address="mis@e.com",
            email_type="primary",
            verified=True,
        )
        event1 = make_event(name="Event 1")
        event2 = make_event(name="Event 2")
        ticket_from_event2 = Ticket.objects.create(event=event2, name="VIP")
        response = self.client.post(
            "/admin/event/eventregistration/add/",
            {
                "member": str(member.pk),
                "event": str(event1.pk),
                "ticket": str(ticket_from_event2.pk),
                "attendee_first_name": "",
                "attendee_last_name": "",
                "attendee_email": "",
                "attendee_secondary_email": "",
                "attendee_phone": "",
                "attendee_organization": "",
                "phone_verified": "",
                "question_answers": "[]",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(EventRegistration.objects.filter(member=member, event=event1).exists())

    def test_has_change_permission(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/admin/")
        request.user = self.admin_user
        admin_instance = EventRegistrationAdmin(EventRegistration, None)
        self.assertTrue(admin_instance.has_change_permission(request))

    def test_change_page_keeps_only_ticket_editable_in_ticket_section(self):
        from django.test import RequestFactory

        event = make_event()
        ticket = make_ticket(event)
        member = make_member(email="readonly-ticket-section@example.com")
        registration = make_registration(member, event, ticket)
        factory = RequestFactory()
        request = factory.get("/admin/")
        request.user = self.admin_user
        admin_instance = EventRegistrationAdmin(EventRegistration, None)

        readonly_fields = admin_instance.get_readonly_fields(request, obj=registration)

        self.assertNotIn("ticket", readonly_fields)
        self.assertIn("event", readonly_fields)
        self.assertIn("member", readonly_fields)
        self.assertIn("ticket_code", readonly_fields)
        self.assertIn("attendee_email", readonly_fields)
        self.assertIn("send_ticket_email_action", readonly_fields)

    def test_change_form_limits_ticket_choices_to_registration_event(self):
        event = make_event(name="Ticket Choice Event")
        current_ticket = make_ticket(event, name="Current Ticket")
        new_ticket = make_ticket(event, name="Upgrade Ticket")
        other_event = make_event(name="Other Ticket Event")
        other_ticket = make_ticket(other_event, name="Other Event Ticket")
        member = make_member(email="ticket-choice@example.com")
        registration = make_registration(member, event, current_ticket)

        response = self.client.get(f"/admin/event/eventregistration/{registration.pk}/change/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="ticket"')
        self.assertContains(response, 'name="_send_ticket_email"')
        self.assertContains(response, "Send ticket email now")
        self.assertNotContains(response, 'name="send_ticket_email"')
        self.assertNotContains(response, "If checked, a confirmation email")
        self.assertContains(response, str(new_ticket))
        self.assertNotContains(response, str(other_ticket))

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
    def test_admin_change_updates_registration_ticket(self, mock_sync):
        event = make_event()
        current_ticket = make_ticket(event, name="General")
        new_ticket = make_ticket(event, name="VIP")
        member = make_member(email="ticket-change@example.com")
        registration = make_registration(member, event, current_ticket)

        mock_sync.reset_mock()
        response = self.client.post(
            f"/admin/event/eventregistration/{registration.pk}/change/",
            {
                "ticket": str(new_ticket.pk),
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        registration.refresh_from_db()
        self.assertEqual(registration.ticket, new_ticket)
        mock_sync.assert_called_once_with(event)

    @patch("apps.event.services.registration_sheet_sync.schedule_registration_sync")
    def test_admin_change_rejects_ticket_from_other_event(self, mock_sync):
        event = make_event(name="Original Event")
        current_ticket = make_ticket(event, name="General")
        other_event = make_event(name="Other Event")
        other_ticket = make_ticket(other_event, name="Other VIP")
        member = make_member(email="ticket-mismatch-change@example.com")
        registration = make_registration(member, event, current_ticket)

        mock_sync.reset_mock()
        response = self.client.post(
            f"/admin/event/eventregistration/{registration.pk}/change/",
            {
                "ticket": str(other_ticket.pk),
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 200)
        registration.refresh_from_db()
        self.assertEqual(registration.ticket, current_ticket)
        mock_sync.assert_not_called()

    @patch("apps.event.services.ticket.mail.send_ticket_email")
    @patch("apps.event.services.registration_sheet_sync.schedule_registration_sync")
    def test_admin_change_send_ticket_button_saves_ticket_and_sends_email(self, mock_sync, mock_send):
        event = make_event()
        current_ticket = make_ticket(event, name="General")
        new_ticket = make_ticket(event, name="VIP")
        member = make_member(email="ticket-send-button@example.com")
        registration = make_registration(member, event, current_ticket)

        mock_sync.reset_mock()
        # The email goes after the admin's transaction commits (no lock is held across the provider call).
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.post(
                f"/admin/event/eventregistration/{registration.pk}/change/",
                {
                    "ticket": str(new_ticket.pk),
                    "_send_ticket_email": "1",
                },
            )

        self.assertTrue(callbacks)
        self.assertRedirects(response, f"/admin/event/eventregistration/{registration.pk}/change/")
        registration.refresh_from_db()
        self.assertEqual(registration.ticket, new_ticket)
        mock_sync.assert_called_once_with(event)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.args[0].pk, registration.pk)
        self.assertEqual(mock_send.call_args.args[0].ticket_id, new_ticket.pk)

    def test_has_delete_permission(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/admin/")
        request.user = self.admin_user
        admin_instance = EventRegistrationAdmin(EventRegistration, None)
        self.assertTrue(admin_instance.has_delete_permission(request))

    def test_search_by_attendee_fields(self):
        member = Member.objects.create_user(password="testpass123")
        ContactEmail.objects.create(member=member, email_address="u@e.com", email_type="primary", verified=True)
        event = make_event()
        ticket = Ticket.objects.create(event=event, name="GA")
        EventRegistration.objects.create(
            member=member,
            event=event,
            ticket=ticket,
            attendee_first_name="Searchable",
            attendee_last_name="Name",
        )
        response = self.client.get("/admin/event/eventregistration/?q=Searchable")
        self.assertEqual(response.status_code, 200)

    def test_member_info_endpoint(self):
        member = Member.objects.create_user(
            password="testpass123",
            first_name="Ada",
            last_name="Lovelace",
            organization="UCM",
            title="Prof",
        )
        ContactEmail.objects.create(
            member=member,
            email_address="ada@e.com",
            email_type="primary",
            verified=True,
        )
        ContactEmail.objects.create(
            member=member,
            email_address="ada2@e.com",
            email_type="secondary",
            verified=False,
        )
        response = self.client.get(f"/admin/event/eventregistration/member-info/{member.pk}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Ada Lovelace")
        self.assertIn("ada@e.com", data["emails"])
        self.assertIn("ada2@e.com", data["emails"])
        self.assertEqual(data["organization"], "UCM")
        self.assertEqual(data["title"], "Prof")

    def test_event_info_endpoint(self):
        event = make_event(
            name="Info Test",
            allow_secondary_email=True,
            end_date="2025-06-17",
            registration_open=True,
            collect_phone=True,
            verify_phone=True,
            require_phone=True,
            verify_secondary_email=True,
            require_secondary_email=True,
        )
        Ticket.objects.create(event=event, name="GA")
        Ticket.objects.create(event=event, name="VIP")
        response = self.client.get(f"/admin/event/eventregistration/event-info/{event.pk}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Info Test")
        self.assertEqual(data["date"], "2025-06-15")
        self.assertEqual(data["end_date"], "2025-06-17")
        self.assertEqual(data["date_range"], "June 15–17, 2025")
        self.assertEqual(data["location"], "Test Venue")
        self.assertNotIn("is_live", data)
        self.assertTrue(data["registration_open"])
        self.assertTrue(data["collect_phone"])
        self.assertTrue(data["verify_phone"])
        self.assertTrue(data["require_phone"])
        self.assertTrue(data["verify_secondary_email"])
        self.assertTrue(data["require_secondary_email"])
        self.assertEqual(data["total_registrations"], 0)
        ticket_names = [t["name"] for t in data["tickets"]]
        self.assertIn("GA", ticket_names)
        self.assertIn("VIP", ticket_names)

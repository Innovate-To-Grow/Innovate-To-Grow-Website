import json

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.event.models import Event
from apps.event.tests.helpers import (
    make_event,
    make_member,
    make_registration,
    make_superuser,
    make_ticket,
)


class _EventRegistrationAdminCase(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class EventRegistrationAdminTest(_EventRegistrationAdminCase):
    def test_changelist_accessible(self):
        response = self.client.get("/admin/event/eventregistration/")
        self.assertEqual(response.status_code, 200)

    def test_changelist_shows_send_all_ticket_emails_button(self):
        response = self.client.get("/admin/event/eventregistration/")
        self.assertContains(response, "Send All Tickets")
        self.assertContains(response, reverse("admin:event_eventregistration_send_all_ticket_emails"))

    def test_export_column_picker_includes_member_information(self):
        event = make_event()
        ticket = make_ticket(event)
        member = make_member(email="export-picker@example.com")
        registration = make_registration(member, event, ticket)

        response = self.client.post(
            "/admin/event/eventregistration/",
            {
                "action": "export_data",
                ACTION_CHECKBOX_NAME: str(registration.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member Title")
        self.assertContains(response, "Member Organization")
        self.assertContains(response, "Member Primary Email")
        self.assertContains(response, "Member Phone Numbers")
        self.assertContains(response, "Event Start Date")
        self.assertContains(response, "Event End Date")
        self.assertNotContains(response, 'value="event_date"')

    def test_export_includes_event_start_and_end_dates(self):
        event = make_event(name="Multi-day Export", date="2025-06-15", end_date="2025-06-17")
        ticket = make_ticket(event)
        member = make_member(email="export-dates@example.com")
        registration = make_registration(member, event, ticket)

        response = self.client.post(
            "/admin/event/eventregistration/",
            {
                "action": "export_data",
                ACTION_CHECKBOX_NAME: str(registration.pk),
                "export_confirm": "1",
                "export_format": "json",
                "export_filename": "registration_dates",
                "export_fields": ["event_date", "event_start_date", "event_end_date"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content),
            [
                {
                    "event_date": "2025-06-15",
                    "event_start_date": "2025-06-15",
                    "event_end_date": "2025-06-17",
                }
            ],
        )

    def test_export_accepts_legacy_event_date_selection(self):
        event = make_event(name="Legacy Export", date="2025-06-15", end_date="2025-06-17")
        ticket = make_ticket(event)
        member = make_member(email="legacy-export-date@example.com")
        registration = make_registration(member, event, ticket)

        response = self.client.post(
            "/admin/event/eventregistration/",
            {
                "action": "export_data",
                ACTION_CHECKBOX_NAME: str(registration.pk),
                "export_confirm": "1",
                "export_format": "json",
                "export_fields": ["event_date"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), [{"event_date": "2025-06-15"}])

    def test_export_old_null_end_date_falls_back_to_start_date(self):
        event = make_event(name="Rolling Deploy Export", date="2025-06-15")
        Event.objects.filter(pk=event.pk).update(end_date=None)
        ticket = make_ticket(event)
        member = make_member(email="export-null-end-date@example.com")
        registration = make_registration(member, event, ticket)

        response = self.client.post(
            "/admin/event/eventregistration/",
            {
                "action": "export_data",
                ACTION_CHECKBOX_NAME: str(registration.pk),
                "export_confirm": "1",
                "export_format": "json",
                "export_filename": "registration_legacy_date",
                "export_fields": ["event_date", "event_start_date", "event_end_date"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content),
            [
                {
                    "event_date": "2025-06-15",
                    "event_start_date": "2025-06-15",
                    "event_end_date": "2025-06-15",
                }
            ],
        )

from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from authn.models import ContactEmail, Member
from event.admin.registration import EventRegistrationAdmin
from event.models import Event, EventRegistration, Ticket
from event.services import ScheduleSyncStats
from event.tests.helpers import make_event, make_superuser


class EventAdminTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_changelist_accessible(self):
        response = self.client.get("/admin/event/event/")
        self.assertEqual(response.status_code, 200)

    def test_add_form_accessible(self):
        response = self.client.get("/admin/event/event/add/")
        self.assertEqual(response.status_code, 200)

    def test_change_page_shows_inlines_for_staff_without_ticket_model_perms(self):
        """Inlines must not depend on event.add_ticket; match Event admin access instead."""
        editor = Member.objects.create_user(password="testpass123", is_staff=True, is_superuser=False)
        ContactEmail.objects.create(
            member=editor, email_address="editor@example.com", email_type="primary", verified=True
        )
        ct = ContentType.objects.get_for_model(Event)
        editor.user_permissions.add(Permission.objects.get(content_type=ct, codename="change_event"))
        event = make_event(name="Inline Perm Test")
        self.client.logout()
        self.client.login(username="editor@example.com", password="testpass123")

        response = self.client.get(f"/admin/event/event/{event.pk}/change/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="tickets-group"')
        self.assertContains(response, 'id="questions-group"')

    def test_search_by_name(self):
        make_event(name="Searchable Event")
        response = self.client.get("/admin/event/event/?q=Searchable")
        self.assertEqual(response.status_code, 200)

    def test_list_filter_by_is_live(self):
        response = self.client.get("/admin/event/event/?is_live__exact=1")
        self.assertEqual(response.status_code, 200)

    @patch("event.admin.current_project.sync_schedule")
    def test_pull_schedule_action_triggers_sync(self, mock_sync):
        from event.models import CurrentProjectSchedule

        mock_sync.return_value = ScheduleSyncStats(sections_created=3, tracks_created=3, slots_created=4)
        config = CurrentProjectSchedule.objects.create(name="Demo Day")

        response = self.client.post("/admin/event/currentprojectschedule/pull/")

        self.assertEqual(response.status_code, 302)
        mock_sync.assert_called_once_with(config)


class EventRegistrationAdminTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_changelist_accessible(self):
        response = self.client.get("/admin/event/eventregistration/")
        self.assertEqual(response.status_code, 200)

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

    @patch("event.services.registration_sheet_sync.schedule_registration_sync")
    def test_admin_add_creates_registration(self, mock_sync):
        member = Member.objects.create_user(password="testpass123")
        ContactEmail.objects.create(member=member, email_address="reg@e.com", email_type="primary", verified=True)
        event = make_event()
        ticket = Ticket.objects.create(event=event, name="GA")
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
        ContactEmail.objects.create(member=member, email_address="dup@e.com", email_type="primary", verified=True)
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
        ContactEmail.objects.create(member=member, email_address="mis@e.com", email_type="primary", verified=True)
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

    def test_has_no_change_permission(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/admin/")
        request.user = self.admin_user
        admin_instance = EventRegistrationAdmin(EventRegistration, None)
        self.assertFalse(admin_instance.has_change_permission(request))

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
            password="testpass123", first_name="Ada", last_name="Lovelace", organization="UCM", title="Prof"
        )
        ContactEmail.objects.create(member=member, email_address="ada@e.com", email_type="primary", verified=True)
        ContactEmail.objects.create(member=member, email_address="ada2@e.com", email_type="secondary", verified=False)
        response = self.client.get(f"/admin/event/eventregistration/member-info/{member.pk}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Ada Lovelace")
        self.assertIn("ada@e.com", data["emails"])
        self.assertIn("ada2@e.com", data["emails"])
        self.assertEqual(data["organization"], "UCM")
        self.assertEqual(data["title"], "Prof")

    def test_event_info_endpoint(self):
        event = make_event(name="Info Test")
        Ticket.objects.create(event=event, name="GA")
        Ticket.objects.create(event=event, name="VIP")
        response = self.client.get(f"/admin/event/eventregistration/event-info/{event.pk}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Info Test")
        self.assertEqual(data["date"], "2025-06-15")
        self.assertEqual(data["location"], "Test Venue")
        self.assertEqual(data["total_registrations"], 0)
        ticket_names = [t["name"] for t in data["tickets"]]
        self.assertIn("GA", ticket_names)
        self.assertIn("VIP", ticket_names)

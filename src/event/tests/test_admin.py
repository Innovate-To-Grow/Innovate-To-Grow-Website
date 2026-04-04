from unittest.mock import patch

from django.test import TestCase

from authn.models import ContactEmail, Member
from event.admin.registration import EventRegistrationAdmin
from event.models import EventRegistration, Ticket
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

    def test_search_by_name(self):
        make_event(name="Searchable Event")
        response = self.client.get("/admin/event/event/?q=Searchable")
        self.assertEqual(response.status_code, 200)

    def test_list_filter_by_is_live(self):
        response = self.client.get("/admin/event/event/?is_live__exact=1")
        self.assertEqual(response.status_code, 200)

    @patch("event.admin.event.sync_event_schedule")
    def test_pull_schedule_action_triggers_sync(self, mock_sync):
        mock_sync.return_value = ScheduleSyncStats(sections_created=3, tracks_created=3, slots_created=4)
        event = make_event(name="Schedule Event")

        response = self.client.get(f"/admin/event/event/{event.pk}/pull-schedule/")

        self.assertEqual(response.status_code, 302)
        mock_sync.assert_called_once_with(event)


class EventRegistrationAdminTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_changelist_accessible(self):
        response = self.client.get("/admin/event/eventregistration/")
        self.assertEqual(response.status_code, 200)

    def test_has_no_add_permission(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/admin/")
        request.user = self.admin_user
        admin_instance = EventRegistrationAdmin(EventRegistration, None)
        self.assertFalse(admin_instance.has_add_permission(request))

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

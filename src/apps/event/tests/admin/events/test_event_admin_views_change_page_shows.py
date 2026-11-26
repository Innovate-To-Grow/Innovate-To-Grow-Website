from unittest.mock import patch

from django.test import override_settings

from apps.authn.models import ContactEmail, Member
from apps.event.models import Event, Question, Ticket
from apps.event.services import ScheduleSyncStats
from apps.event.tests.admin.events.test_event_admin_views import _EventAdminCase
from apps.event.tests.helpers import (
    make_event,
)


class EventAdminTest(_EventAdminCase):
    def test_change_page_shows_inlines_for_an_admin(self):
        """Inlines match Event admin access (every Admin), not per-model Django
        permissions — see apps.core.utils.access.user_can_access_app."""
        editor = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(
            member=editor,
            email_address="editor@example.com",
            email_type="primary",
            verified=True,
        )
        event = make_event(name="Inline Perm Test")
        self.client.logout()
        self.client.login(username="editor@example.com", password="testpass123")

        response = self.client.get(f"/admin/event/event/{event.pk}/change/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="tickets-group"')
        self.assertContains(response, 'id="questions-group"')

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_an_admin_can_load_and_save_copied_children(self):
        source = make_event(name="Staff Copy Source")
        Ticket.objects.create(event=source, name="Staff Ticket", order=1)
        Question.objects.create(event=source, text="Staff question?", is_required=True, order=2)
        editor = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(
            member=editor,
            email_address="copy-editor@example.com",
            email_type="primary",
            verified=True,
        )
        self.client.logout()
        self.client.login(username="copy-editor@example.com", password="testpass123")

        loaded = self.client.get(f"/admin/event/event/add/?copy_from={source.pk}")

        self.assertEqual(loaded.status_code, 200)
        self.assertContains(loaded, 'value="Staff Ticket"')
        self.assertContains(loaded, 'value="Staff question?"')
        saved = self.client.post(
            f"/admin/event/event/add/?copy_from={source.pk}",
            self._copy_post_data(
                name="Staff Saved Copy",
                slug="staff-saved-copy",
                ticket_rows=[{"name": "Staff Ticket", "order": 1}],
                question_rows=[{"text": "Staff question?", "is_required": True, "order": 2}],
            ),
        )
        self.assertEqual(saved.status_code, 302)
        self.assertIn("confirm-change", saved.url)
        self.assertEqual(self.client.get(saved.url).status_code, 200)
        pending = self.client.session["_admin_pending_change_event_event"]
        saved = self.client.post(
            saved.url,
            {"token": pending["token"], "confirmation_word": "event"},
        )
        self.assertEqual(saved.status_code, 302)
        copied = Event.objects.get(slug="staff-saved-copy")
        self.assertEqual(copied.tickets.get().name, "Staff Ticket")
        self.assertEqual(copied.questions.get().text, "Staff question?")

    def test_search_by_name(self):
        make_event(name="Searchable Event")
        response = self.client.get("/admin/event/event/?q=Searchable")
        self.assertEqual(response.status_code, 200)

    def test_list_filter_by_registration_open(self):
        response = self.client.get("/admin/event/event/?registration_open__exact=1")
        self.assertEqual(response.status_code, 200)

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
    def test_pull_schedule_action_triggers_sync(self, mock_sync):
        from apps.event.models import CurrentProjectSchedule

        mock_sync.return_value = ScheduleSyncStats(sections_created=3, tracks_created=3, slots_created=4)
        config = CurrentProjectSchedule.objects.create(name="Demo Day")

        response = self.client.post("/admin/event/currentprojectschedule/pull/")

        self.assertEqual(response.status_code, 302)
        mock_sync.assert_called_once_with(config, sync_type="manual")

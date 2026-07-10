import datetime
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from apps.event.admin.event import EventAdmin, EventAdminForm, QuestionInline, TicketInline
from apps.event.models import Event
from apps.event.services.registration_sheet_sync import RegistrationSyncError
from apps.event.tests.helpers import make_event, make_superuser


class EmptyAdminSite(AdminSite):
    """An admin site with no models registered (Event lookup returns None)."""


class EventRelatedInlineFallbackTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = make_superuser(email="inline-admin@example.com")
        self.empty_site = EmptyAdminSite()

    def _request(self):
        request = self.factory.get("/admin/")
        request.user = self.user
        return request

    def test_view_permission_falls_back_when_event_admin_missing(self):
        inline = TicketInline(Event, self.empty_site)
        # super().has_view_permission on a TabularInline without Event admin defers to default perms.
        self.assertTrue(inline.has_view_permission(self._request()))

    def test_add_permission_falls_back_when_event_admin_missing(self):
        inline = TicketInline(Event, self.empty_site)
        self.assertTrue(inline.has_add_permission(self._request()))

    def test_change_permission_falls_back_when_event_admin_missing(self):
        inline = QuestionInline(Event, self.empty_site)
        self.assertTrue(inline.has_change_permission(self._request()))

    def test_delete_permission_falls_back_when_event_admin_missing(self):
        inline = QuestionInline(Event, self.empty_site)
        self.assertTrue(inline.has_delete_permission(self._request()))


class EventAdminBadgeTest(TestCase):
    def setUp(self):
        self.admin = EventAdmin(Event, AdminSite())

    def test_secondary_email_badge_on(self):
        self.assertEqual(self.admin.secondary_email_badge(Event(allow_secondary_email=True)), ("on", "On"))

    def test_secondary_email_badge_off(self):
        self.assertEqual(self.admin.secondary_email_badge(Event(allow_secondary_email=False)), ("off", "Off"))

    def test_phone_badge_verified(self):
        self.assertEqual(
            self.admin.phone_badge(Event(collect_phone=True, verify_phone=True)),
            ("prompt_verify", "Prompt + verification"),
        )

    def test_phone_badge_collect(self):
        self.assertEqual(
            self.admin.phone_badge(Event(collect_phone=True, verify_phone=False)),
            ("prompt", "Prompt"),
        )

    def test_phone_badge_off(self):
        self.assertEqual(self.admin.phone_badge(Event(collect_phone=False, verify_phone=False)), ("off", "Off"))

    def test_date_range_collapses_single_day(self):
        event = Event(date=datetime.date(2026, 5, 14), end_date=datetime.date(2026, 5, 14))
        self.assertEqual(self.admin.date_range(event), "May 14, 2026")

    def test_date_range_displays_multiple_days(self):
        event = Event(date=datetime.date(2026, 5, 31), end_date=datetime.date(2026, 6, 2))
        self.assertEqual(self.admin.date_range(event), "May 31–June 2, 2026")

    def test_change_form_prefills_transitional_null_end_date(self):
        event = make_event(name="Legacy single-day Event")
        Event.objects.filter(pk=event.pk).update(end_date=None)
        event.refresh_from_db()

        form = EventAdminForm(instance=event)

        self.assertEqual(form.initial["end_date"], event.date)


class EventAdminSyncActionTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = make_superuser(email="sync-action-admin@example.com")
        self.admin = EventAdmin(Event, AdminSite())
        self.event = make_event(name="Sync Action Event")

    def _request(self):
        request = self.factory.post("/admin/")
        request.user = self.user
        request.session = "session"
        request._messages = FallbackStorage(request)
        return request

    @patch("apps.event.services.registration_sheet_sync.sync_registrations_to_sheet", return_value=7)
    def test_action_reports_success(self, mock_sync):
        request = self._request()
        self.admin.sync_registrations_to_sheet(request, Event.objects.filter(pk=self.event.pk))

        mock_sync.assert_called_once()
        messages = [str(m) for m in request._messages]
        self.assertTrue(any("Synced 7 registrations" in m for m in messages))

    @patch(
        "apps.event.services.registration_sheet_sync.sync_registrations_to_sheet",
        side_effect=RegistrationSyncError("not configured"),
    )
    def test_action_reports_failure(self, mock_sync):
        request = self._request()
        self.admin.sync_registrations_to_sheet(request, Event.objects.filter(pk=self.event.pk))

        messages = [str(m) for m in request._messages]
        self.assertTrue(any("Sync failed" in m and "not configured" in m for m in messages))

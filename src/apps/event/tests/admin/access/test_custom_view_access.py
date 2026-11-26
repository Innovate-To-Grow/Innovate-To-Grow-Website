"""Access to the event app's custom admin URLs.

Every custom URL is wrapped in ``self.admin_site.admin_view(...)``, so a regular member is redirected to the admin login
before the view runs. Each view also re-checks the ModelAdmin's permission hook (defence in depth), exercised here by
calling it directly with a non-Admin request. Every Admin is allowed through.
"""

from unittest.mock import patch

from django.contrib import admin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.event.models import CheckIn, CurrentProjectSchedule, EventRegistration
from apps.event.tests.helpers import make_admin, make_event, make_member, make_registration, make_ticket


class EventCustomViewAccessTest(TestCase):
    """Drive every event ``admin_view``-wrapped custom URL through the full admin request stack."""

    def setUp(self):
        cache.clear()
        self.outsider = make_member(email="plain@example.com", first_name="Out", last_name="Sider")
        self.admin_user = make_admin(email="event-admin@example.com", first_name="Eve", last_name="Ent")

        self.event = make_event(name="Demo Day")
        self.ticket = make_ticket(self.event, name="GA")
        self.member = make_member(email="reg-member@example.com", first_name="Reg", last_name="Member")
        self.registration = make_registration(self.member, self.event, self.ticket)
        self.check_in = CheckIn.objects.create(event=self.event, name="Main Door")
        self.schedule = CurrentProjectSchedule.objects.create(name="Demo Day")

    def tearDown(self):
        cache.clear()

    def custom_urls(self):
        return [
            ("post", reverse("admin:event_currentprojectschedule_pull")),
            ("get", reverse("admin:event_currentprojectschedule_pull")),
            ("get", reverse("admin:event_currentprojectschedule_sync_from_google_sheets", args=[self.schedule.pk])),
            (
                "get",
                reverse("admin:event_currentprojectschedule_sync_from_google_sheets_detail", args=[self.schedule.pk]),
            ),
            ("post", reverse("admin:event_currentprojectschedule_save_sync_settings")),
            ("get", reverse("admin:event_eventregistration_send_all_ticket_emails")),
            ("post", reverse("admin:event_eventregistration_send_all_ticket_emails")),
            ("get", reverse("admin:reg-member-info", args=[self.member.pk])),
            ("get", reverse("admin:reg-event-info", args=[self.event.pk])),
            ("get", reverse("admin:event_checkin_scanner", args=[self.check_in.pk])),
            ("get", reverse("admin:event_checkin_export", args=[self.check_in.pk])),
        ]

    @patch("apps.event.services.ticket.mail.send_ticket_email")
    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
    def test_a_regular_member_is_sent_to_the_login_and_nothing_runs(self, mock_sync, mock_send):
        self.client.force_login(self.outsider)

        for method, url in self.custom_urls():
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, {})
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])
        mock_sync.assert_not_called()
        mock_send.assert_not_called()

    def test_the_views_refuse_a_non_admin_even_when_called_directly(self):
        request = RequestFactory().get("/")
        request.user = self.outsider
        schedule_admin = admin.site._registry[CurrentProjectSchedule]
        registration_admin = admin.site._registry[EventRegistration]
        checkin_admin = admin.site._registry[CheckIn]
        calls = [
            lambda: schedule_admin.pull_view(request),
            lambda: schedule_admin.save_sync_settings_view(request),
            lambda: registration_admin.send_all_ticket_emails_view(request),
            lambda: registration_admin._member_info_view(request, self.member.pk),
            lambda: registration_admin._event_info_view(request, self.event.pk),
            lambda: checkin_admin.scanner_view(request, str(self.check_in.pk)),
            lambda: checkin_admin.export_view(request, str(self.check_in.pk)),
        ]
        for index, call in enumerate(calls):
            with self.subTest(view=index), self.assertRaises(PermissionDenied):
                call()

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
    def test_pull_view_allowed_for_an_admin(self, mock_sync):
        self.client.force_login(self.admin_user)
        resp = self.client.post(reverse("admin:event_currentprojectschedule_pull"))
        self.assertRedirects(
            resp, reverse("admin:event_currentprojectschedule_changelist"), fetch_redirect_response=False
        )
        mock_sync.assert_called_once()

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
    def test_sync_from_google_sheets_action_allowed_for_an_admin(self, _mock_sync):
        self.client.force_login(self.admin_user)
        url = reverse("admin:event_currentprojectschedule_sync_from_google_sheets", args=[self.schedule.pk])
        self.assertNotEqual(self.client.get(url).status_code, 403)

    def test_save_sync_settings_allowed_for_an_admin(self):
        self.client.force_login(self.admin_user)
        resp = self.client.post(
            reverse("admin:event_currentprojectschedule_save_sync_settings"),
            {"auto_sync_enabled": "1", "sync_interval_minutes": "30"},
        )
        self.assertNotEqual(resp.status_code, 403)
        self.assertNotIn("/login/", resp.get("Location", ""))

    @patch("apps.event.services.ticket.mail.send_ticket_email")
    def test_send_all_ticket_emails_allowed_for_an_admin(self, _mock_send):
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse("admin:event_eventregistration_send_all_ticket_emails"))
        self.assertNotEqual(resp.status_code, 403)
        self.assertNotIn("/login/", resp.get("Location", ""))

    def test_info_views_allowed_for_an_admin(self):
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get(reverse("admin:reg-member-info", args=[self.member.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:reg-event-info", args=[self.event.pk])).status_code, 200)

    def test_checkin_views_allowed_for_an_admin(self):
        self.client.force_login(self.admin_user)
        scanner = self.client.get(reverse("admin:event_checkin_scanner", args=[self.check_in.pk]))
        export = self.client.get(reverse("admin:event_checkin_export", args=[self.check_in.pk]))
        self.assertEqual((scanner.status_code, export.status_code), (200, 200))

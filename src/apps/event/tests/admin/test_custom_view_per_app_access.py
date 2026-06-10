"""Privilege-escalation regression tests for the event app's custom admin URLs.

Custom admin URLs registered via ``self.admin_site.admin_view(...)`` are gated by
Django only on ``is_staff``/``is_active`` — the per-app access model
(``apps.core.access.user_can_access_app`` via ``BaseModelAdmin`` permission hooks)
is NOT run for them. Each of these views therefore re-checks event-app access at
entry and raises ``PermissionDenied`` (rendered as HTTP 403 by the test client).

A staff member whose ``admin_apps`` lacks ``event`` must get 403; an event-granted
staff member (or a superuser) must be allowed (not 403).
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.event.models import CheckIn, CurrentProjectSchedule
from apps.event.tests.helpers import (
    make_admin,
    make_event,
    make_member,
    make_registration,
    make_superuser,
    make_ticket,
)


class EventCustomViewPerAppAccessTest(TestCase):
    """Drive every event ``admin_view``-wrapped custom URL through the full admin
    request stack and assert per-app authorization."""

    def setUp(self):
        cache.clear()
        # Staff WITHOUT the event app — must be denied (403) on every custom view.
        self.outsider = make_admin(apps=["cms"], email="cms-only@example.com", first_name="Out", last_name="Sider")
        # Staff WITH the event app — must be allowed (not 403).
        self.event_staff = make_admin(
            apps=["event"], email="event-staff@example.com", first_name="Eve", last_name="Ent"
        )
        # I2G Master — bypasses the per-app list.
        self.superuser = make_superuser(email="event-master@example.com")

        self.event = make_event(name="Demo Day")
        self.ticket = make_ticket(self.event, name="GA")
        self.member = make_member(email="reg-member@example.com", first_name="Reg", last_name="Member")
        self.registration = make_registration(self.member, self.event, self.ticket)
        self.check_in = CheckIn.objects.create(event=self.event, name="Main Door")

    def tearDown(self):
        cache.clear()

    # ----- current_project.py: pull_view + save_sync_settings_view -----

    def test_pull_view_denied_for_non_event_staff(self):
        self.client.force_login(self.outsider)
        url = reverse("admin:event_currentprojectschedule_pull")
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertEqual(self.client.get(url).status_code, 403)

    @patch("apps.event.admin.current_project.sync_schedule")
    def test_pull_view_allowed_for_event_staff(self, _mock_sync):
        self.client.force_login(self.event_staff)
        resp = self.client.post(reverse("admin:event_currentprojectschedule_pull"))
        self.assertNotEqual(resp.status_code, 403)

    def test_save_sync_settings_denied_for_non_event_staff(self):
        self.client.force_login(self.outsider)
        url = reverse("admin:event_currentprojectschedule_save_sync_settings")
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_save_sync_settings_allowed_for_superuser(self):
        CurrentProjectSchedule.objects.create(name="Demo Day")
        self.client.force_login(self.superuser)
        resp = self.client.post(
            reverse("admin:event_currentprojectschedule_save_sync_settings"),
            {"auto_sync_enabled": "1", "sync_interval_minutes": "30"},
        )
        self.assertNotEqual(resp.status_code, 403)

    # ----- registration/ticket_emails.py: send_all_ticket_emails_view -----

    def test_send_all_ticket_emails_denied_for_non_event_staff(self):
        self.client.force_login(self.outsider)
        url = reverse("admin:event_eventregistration_send_all_ticket_emails")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)

    @patch("apps.event.services.ticket_mail.send_ticket_email")
    def test_send_all_ticket_emails_allowed_for_event_staff(self, _mock_send):
        self.client.force_login(self.event_staff)
        resp = self.client.get(reverse("admin:event_eventregistration_send_all_ticket_emails"))
        self.assertNotEqual(resp.status_code, 403)

    # ----- registration/info_views.py: _member_info_view + _event_info_view -----

    def test_member_info_view_denied_for_non_event_staff(self):
        self.client.force_login(self.outsider)
        url = reverse("admin:reg-member-info", args=[self.member.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_member_info_view_allowed_for_event_staff(self):
        self.client.force_login(self.event_staff)
        resp = self.client.get(reverse("admin:reg-member-info", args=[self.member.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_event_info_view_denied_for_non_event_staff(self):
        self.client.force_login(self.outsider)
        url = reverse("admin:reg-event-info", args=[self.event.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_event_info_view_allowed_for_superuser(self):
        self.client.force_login(self.superuser)
        resp = self.client.get(reverse("admin:reg-event-info", args=[self.event.pk]))
        self.assertEqual(resp.status_code, 200)

    # ----- checkin.py: scanner_view + export_view -----

    def test_scanner_view_denied_for_non_event_staff(self):
        self.client.force_login(self.outsider)
        url = reverse("admin:event_checkin_scanner", args=[self.check_in.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_scanner_view_allowed_for_event_staff(self):
        self.client.force_login(self.event_staff)
        resp = self.client.get(reverse("admin:event_checkin_scanner", args=[self.check_in.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_export_view_denied_for_non_event_staff(self):
        self.client.force_login(self.outsider)
        url = reverse("admin:event_checkin_export", args=[self.check_in.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_export_view_allowed_for_superuser(self):
        self.client.force_login(self.superuser)
        resp = self.client.get(reverse("admin:event_checkin_export", args=[self.check_in.pk]))
        self.assertEqual(resp.status_code, 200)

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import Http404
from django.test import RequestFactory, TestCase

from apps.event.admin.checkin import CheckInAdmin
from apps.event.admin.registration import EventRegistrationAdmin
from apps.event.models import CheckIn, EventRegistration
from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket


class CheckInAdminUnitTest(TestCase):
    def setUp(self):
        self.admin = CheckInAdmin(CheckIn, AdminSite())
        self.factory = RequestFactory()
        self.user = make_superuser(email="checkin-unit-admin@example.com")
        self.event = make_event(name="Console Event")

    def test_is_active_badge_active(self):
        self.assertEqual(self.admin.is_active_badge(CheckIn(is_active=True)), ("Active", "success"))

    def test_is_active_badge_closed(self):
        self.assertEqual(self.admin.is_active_badge(CheckIn(is_active=False)), ("Closed", "info"))

    def test_scanner_link_returns_dash_for_unsaved(self):
        unsaved = CheckIn(event=self.event, name="Pending")
        unsaved.pk = None
        self.assertEqual(self.admin.scanner_link(unsaved), "-")

    def test_scanner_link_renders_anchor_for_saved(self):
        check_in = CheckIn.objects.create(event=self.event, name="Main")
        html = self.admin.scanner_link(check_in)
        self.assertIn("Open Console", html)
        self.assertIn("href", html)

    def _request(self):
        request = self.factory.get("/admin/")
        request.user = self.user
        return request

    def test_scanner_view_missing_checkin_raises_404(self):
        with self.assertRaises(Http404):
            self.admin.scanner_view(self._request(), "00000000-0000-0000-0000-000000000000")

    def test_export_view_missing_checkin_raises_404(self):
        with self.assertRaises(Http404):
            self.admin.export_view(self._request(), "00000000-0000-0000-0000-000000000000")


class TicketEmailMixinUnitTest(TestCase):
    def setUp(self):
        self.admin = EventRegistrationAdmin(EventRegistration, AdminSite())
        self.factory = RequestFactory()
        self.user = make_superuser(email="ticket-mixin-admin@example.com")
        self.event = make_event(name="Mixin Event")
        self.ticket = make_ticket(self.event, name="GA")
        self.member = make_member(email="mixin-member@example.com", first_name="Ada", last_name="Lovelace")
        self.registration = make_registration(self.member, self.event, self.ticket)

    def _request(self):
        request = self.factory.post("/admin/")
        request.user = self.user
        request.session = "session"
        request._messages = FallbackStorage(request)
        return request

    def test_send_ticket_email_action_returns_dash_for_none(self):
        self.assertEqual(self.admin.send_ticket_email_action(None), "-")

    def test_send_ticket_email_action_renders_button(self):
        html = self.admin.send_ticket_email_action(self.registration)
        self.assertIn("Send ticket email now", html)
        self.assertIn("_send_ticket_email", html)

    @patch("apps.event.services.ticket_mail.send_ticket_email", side_effect=RuntimeError("smtp down"))
    def test_send_single_failure_adds_error_message(self, _mock_send):
        request = self._request()
        result = self.admin._send_ticket_email_registration(request, self.registration)
        self.assertFalse(result)
        messages = [str(m) for m in request._messages]
        self.assertTrue(any("Failed to send email" in m for m in messages))

    @patch("apps.event.services.ticket_mail.send_ticket_email")
    def test_resend_ticket_email_action_sends_batch(self, mock_send):
        request = self._request()
        self.admin.resend_ticket_email(request, EventRegistration.objects.filter(pk=self.registration.pk))
        mock_send.assert_called_once()
        messages = [str(m) for m in request._messages]
        self.assertTrue(any("Sent ticket email to 1 registration" in m for m in messages))

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from apps.event.admin.registration import EventRegistrationAdmin
from apps.event.models import EventRegistration
from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket


class RegistrationInfoViewsNotFoundTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser(email="info-admin@example.com")
        self.client.login(username="info-admin@example.com", password="testpass123")
        self.missing_uuid = "00000000-0000-0000-0000-000000000000"

    def test_member_info_returns_404_for_missing_member(self):
        response = self.client.get(f"/admin/event/eventregistration/member-info/{self.missing_uuid}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Not found")

    def test_event_info_returns_404_for_missing_event(self):
        response = self.client.get(f"/admin/event/eventregistration/event-info/{self.missing_uuid}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Not found")


class RegistrationSaveModelTest(TestCase):
    def setUp(self):
        self.admin = EventRegistrationAdmin(EventRegistration, AdminSite())
        self.factory = RequestFactory()
        self.user = make_superuser(email="savemodel-admin@example.com")
        self.event = make_event(name="Save Model Event")
        self.ticket = make_ticket(self.event, name="GA")
        self.member = make_member(email="savemodel-member@example.com")

    def _request(self):
        request = self.factory.post("/admin/")
        request.user = self.user
        request.session = "session"
        request._messages = FallbackStorage(request)
        return request

    def test_save_model_rolls_back_if_durable_scheduling_fails(self):
        registration = make_registration(self.member, self.event, self.ticket)
        original_name = registration.attendee_first_name

        class _Form:
            cleaned_data = {}

        registration.attendee_first_name = "Unsaved change"
        with (
            patch(
                "apps.event.services.registration_sheet_sync.schedule_registration_sync",
                side_effect=RuntimeError("outbox unavailable"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.admin.save_model(self._request(), registration, _Form(), change=True)

        registration.refresh_from_db()
        self.assertEqual(registration.attendee_first_name, original_name)


class RevokeLoginLinksActionTest(TestCase):
    """ "Revoke login links" also ends the registration's SMS ticket links (security review L4)."""

    def setUp(self):
        self.admin = EventRegistrationAdmin(EventRegistration, AdminSite())
        self.factory = RequestFactory()
        self.user = make_superuser(email="revoke-admin@example.com")
        event = make_event(name="Revoke Event")
        self.registration = make_registration(make_member(email="revoke-member@example.com"), event, make_ticket(event))

    def test_ticket_email_and_ticket_text_links_are_revoked(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.mail.models import SmsLinkToken

        live = SmsLinkToken.objects.create(
            token_hash="a" * 64,
            purpose="ticket",
            registration=self.registration,
            redirect_path="/account",
            expires_at=timezone.now() + timedelta(days=3),
        )
        request = self.factory.post("/admin/")
        request.user = self.user
        request.session = "session"
        request._messages = FallbackStorage(request)

        self.admin.revoke_login_links_action(request, EventRegistration.objects.filter(pk=self.registration.pk))

        live.refresh_from_db()
        self.assertLessEqual(live.expires_at, timezone.now())
        self.assertIsNotNone(live.revoked_at)
        self.assertIn("Revoked 1 login link(s).", [str(message) for message in request._messages])

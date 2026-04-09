import datetime
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from event.models import Ticket
from event.services.ticket_assets import (
    build_backend_absolute_url,
    build_frontend_absolute_url,
    build_ticket_access_token,
    build_ticket_login_token,
    generate_ticket_barcode_data_url,
    get_event_datetime,
    get_member_from_login_token,
    get_registration_from_access_token,
)
from event.tests.helpers import make_event, make_member, make_registration

# ---------- Ticket Access Token ----------


class BuildTicketAccessTokenTest(TestCase):
    def setUp(self):
        self.member = make_member()
        self.event = make_event()
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = make_registration(self.member, self.event, self.ticket)

    def test_returns_non_empty_string(self):
        token = build_ticket_access_token(self.registration)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)

    def test_roundtrip_with_get_registration(self):
        token = build_ticket_access_token(self.registration)
        result = get_registration_from_access_token(token)
        self.assertEqual(result.pk, self.registration.pk)


class GetRegistrationFromAccessTokenTest(TestCase):
    def setUp(self):
        self.member = make_member()
        self.event = make_event()
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = make_registration(self.member, self.event, self.ticket)

    def test_valid_token_returns_registration(self):
        token = build_ticket_access_token(self.registration)
        result = get_registration_from_access_token(token)
        self.assertEqual(result.pk, self.registration.pk)

    def test_invalid_token_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_registration_from_access_token("invalid-garbage-token")

    def test_tampered_token_raises_value_error(self):
        token = build_ticket_access_token(self.registration)
        with self.assertRaises(ValueError):
            get_registration_from_access_token(token + "tampered")

    def test_deleted_registration_raises_value_error(self):
        token = build_ticket_access_token(self.registration)
        self.registration.delete()
        with self.assertRaises(ValueError):
            get_registration_from_access_token(token)

    def test_expired_token_raises_value_error(self):
        with patch("django.core.signing.time.time", return_value=1_000_000):
            token = build_ticket_access_token(self.registration)

        with patch("django.core.signing.time.time", return_value=1_000_000 + (60 * 60 * 24 * 30) + 1):
            with self.assertRaises(ValueError):
                get_registration_from_access_token(token)


# ---------- Ticket Login Token ----------


class BuildTicketLoginTokenTest(TestCase):
    def setUp(self):
        self.member = make_member()

    def test_returns_non_empty_string(self):
        token = build_ticket_login_token(self.member)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)

    def test_roundtrip_with_get_member(self):
        token = build_ticket_login_token(self.member)
        result = get_member_from_login_token(token)
        self.assertEqual(result.pk, self.member.pk)


class GetMemberFromLoginTokenTest(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.member = make_member()

    def test_valid_token_returns_member(self):
        token = build_ticket_login_token(self.member)
        result = get_member_from_login_token(token)
        self.assertEqual(result.pk, self.member.pk)

    def test_invalid_token_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_member_from_login_token("invalid-garbage-token")

    def test_inactive_member_raises_value_error(self):
        token = build_ticket_login_token(self.member)
        self.member.is_active = False
        self.member.save()
        with self.assertRaises(ValueError):
            get_member_from_login_token(token)

    def test_nonexistent_member_raises_value_error(self):
        token = build_ticket_login_token(self.member)
        self.member.delete()
        with self.assertRaises(ValueError):
            get_member_from_login_token(token)

    def test_token_can_only_be_used_once(self):
        token = build_ticket_login_token(self.member)
        result = get_member_from_login_token(token)

        self.assertEqual(result.pk, self.member.pk)
        with self.assertRaisesMessage(ValueError, "This login link has already been used."):
            get_member_from_login_token(token)


# ---------- URL Builders ----------


class BuildBackendAbsoluteUrlTest(SimpleTestCase):
    @override_settings(BACKEND_URL="https://api.example.com")
    def test_with_backend_url_setting(self):
        result = build_backend_absolute_url("/event/my-tickets/")
        self.assertEqual(result, "https://api.example.com/event/my-tickets/")

    @override_settings(BACKEND_URL="", FRONTEND_URL="https://www.example.com")
    def test_fallback_to_frontend_url(self):
        result = build_backend_absolute_url("/event/my-tickets/")
        self.assertEqual(result, "https://www.example.com/event/my-tickets/")

    @override_settings(BACKEND_URL="", FRONTEND_URL="")
    def test_no_settings_returns_path_only(self):
        result = build_backend_absolute_url("/event/my-tickets/")
        self.assertEqual(result, "/event/my-tickets/")

    def test_with_request_uses_build_absolute_uri(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/event/my-tickets/")
        result = build_backend_absolute_url("/event/my-tickets/", request=request)
        self.assertIn("/event/my-tickets/", result)
        self.assertTrue(result.startswith("http"))


class BuildFrontendAbsoluteUrlTest(SimpleTestCase):
    @override_settings(FRONTEND_URL="https://www.example.com")
    def test_with_frontend_url_setting(self):
        result = build_frontend_absolute_url("/tickets")
        self.assertEqual(result, "https://www.example.com/tickets")

    @override_settings(FRONTEND_URL="")
    def test_no_setting_no_request_returns_path(self):
        result = build_frontend_absolute_url("/tickets")
        self.assertEqual(result, "/tickets")

    @override_settings(FRONTEND_URL="")
    def test_fallback_to_request(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/tickets")
        result = build_frontend_absolute_url("/tickets", request=request)
        self.assertTrue(result.startswith("http"))


# ---------- Barcode Generation ----------


class GenerateTicketBarcodeDataUrlTest(TestCase):
    def setUp(self):
        self.member = make_member()
        self.event = make_event()
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = make_registration(self.member, self.event, self.ticket)

    def test_returns_data_uri_prefix(self):
        result = generate_ticket_barcode_data_url(self.registration)
        self.assertTrue(result.startswith("data:image/png;base64,"))

    def test_returns_valid_base64(self):
        import base64

        result = generate_ticket_barcode_data_url(self.registration)
        b64_data = result.split(",", 1)[1]
        decoded = base64.b64decode(b64_data)
        self.assertTrue(len(decoded) > 0)


# ---------- get_event_datetime ----------


class GetEventDatetimeTest(TestCase):
    def test_returns_datetime_from_date(self):
        event = make_event(date=datetime.date(2025, 6, 15))
        result = get_event_datetime(event)
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 15)

    def test_naive_date_made_aware(self):
        from django.utils import timezone

        event = make_event(date=datetime.date(2025, 6, 15))
        result = get_event_datetime(event)
        self.assertFalse(timezone.is_naive(result))

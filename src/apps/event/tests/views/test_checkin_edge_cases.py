from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import CheckIn, CheckInRecord
from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket
from apps.event.views.checkin.payloads import parse_ticket_code


class CheckInScanEdgeCaseTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_superuser(email="scan-edge-admin@example.com")
        self.client.force_authenticate(self.admin)
        self.event = make_event(name="Scan Edge Event")
        self.ticket = make_ticket(self.event, name="GA")
        self.member = make_member(email="scan-edge@example.com", first_name="Ada", last_name="Lovelace")
        self.registration = make_registration(self.member, self.event, self.ticket)
        self.check_in = CheckIn.objects.create(event=self.event, name="Main")
        self.missing_uuid = "00000000-0000-0000-0000-000000000000"

    def test_scan_missing_checkin_returns_404(self):
        response = self.client.post(
            f"/event/check-in/{self.missing_uuid}/scan/",
            {"ticket_code": self.registration.ticket_code},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["status"], "error")
        self.assertEqual(response.data["detail"], "Check-in session not found.")

    def test_integrity_error_without_existing_record_returns_409(self):
        class RacingQuerySet:
            def get_or_create(self, *args, **kwargs):
                # Simulate a unique-constraint violation without persisting a record,
                # so the recovery lookup finds nothing.
                raise IntegrityError("phantom conflict")

        with patch(
            "apps.event.views.checkin.CheckInRecord.objects.select_related",
            return_value=RacingQuerySet(),
        ):
            response = self.client.post(
                f"/event/check-in/{self.check_in.pk}/scan/",
                {"ticket_code": self.registration.ticket_code},
                format="json",
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["status"], "error")
        self.assertIn("Could not finalize check-in", response.data["detail"])
        self.assertFalse(CheckInRecord.objects.filter(registration=self.registration).exists())

    def test_status_missing_checkin_returns_404(self):
        response = self.client.get(f"/event/check-in/{self.missing_uuid}/status/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"], "Check-in session not found.")

    def test_undo_missing_checkin_returns_404(self):
        response = self.client.post(
            f"/event/check-in/{self.missing_uuid}/records/{self.missing_uuid}/undo/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["status"], "error")
        self.assertEqual(response.data["detail"], "Check-in session not found.")


class ParseTicketCodePipeTest(TestCase):
    def test_pipe_delimited_payload_extracts_code(self):
        # No bare ticket-code match, so the pipe-delimited I2G|EVENT|...|CODE path runs.
        result = parse_ticket_code("I2G|EVENT|some-event|abc123token")
        self.assertEqual(result, "abc123token")

    def test_pipe_payload_without_i2g_prefix_returns_raw(self):
        result = parse_ticket_code("FOO|BAR|baz|qux")
        self.assertEqual(result, "FOO|BAR|baz|qux")

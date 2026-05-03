from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from event.models import CheckIn, CheckInRecord
from event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket


class CheckInApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_superuser(email="checkin-admin@example.com")
        self.client.force_authenticate(self.admin)
        self.event = make_event(name="Check-in Event")
        self.ticket = make_ticket(self.event, name="General")
        self.member = make_member(email="checkin-attendee@example.com", first_name="Ada", last_name="Lovelace")
        self.registration = make_registration(self.member, self.event, self.ticket)
        self.check_in = CheckIn.objects.create(event=self.event, name="Main Entrance")
        self.other_check_in = CheckIn.objects.create(event=self.event, name="Side Entrance")

    def scan_url(self, check_in=None):
        check_in = check_in or self.check_in
        return f"/event/check-in/{check_in.pk}/scan/"

    def status_url(self, check_in=None):
        check_in = check_in or self.check_in
        return f"/event/check-in/{check_in.pk}/status/"

    def undo_url(self, record, check_in=None):
        check_in = check_in or self.check_in
        return f"/event/check-in/{check_in.pk}/records/{record.pk}/undo/"

    def test_scan_raw_ticket_code_checks_in(self):
        response = self.client.post(self.scan_url(), {"ticket_code": self.registration.ticket_code}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["attendee"]["ticket_code"], self.registration.ticket_code)
        self.assertEqual(response.data["station_scan_count"], 1)
        self.assertTrue(CheckInRecord.objects.filter(registration=self.registration, check_in=self.check_in).exists())

    def test_scan_barcode_payload_checks_in(self):
        response = self.client.post(self.scan_url(), {"barcode": self.registration.barcode_payload}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["record_id"], str(CheckInRecord.objects.get().pk))

    def test_second_station_scan_is_event_wide_duplicate(self):
        record = CheckInRecord.objects.create(check_in=self.other_check_in, registration=self.registration)

        response = self.client.post(self.scan_url(), {"ticket_code": self.registration.ticket_code}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "duplicate")
        self.assertEqual(response.data["record_id"], str(record.pk))
        self.assertEqual(response.data["existing_check_in"]["id"], str(self.other_check_in.pk))
        self.assertEqual(CheckInRecord.objects.filter(registration=self.registration).count(), 1)

    def test_inactive_checkin_rejects_scan(self):
        self.check_in.is_active = False
        self.check_in.save(update_fields=["is_active", "updated_at"])

        response = self.client.post(self.scan_url(), {"ticket_code": self.registration.ticket_code}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["status"], "error")

    def test_unknown_ticket_code_returns_not_found(self):
        response = self.client.post(self.scan_url(), {"ticket_code": "I2G-MISSING"}, format="json")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["status"], "not_found")

    def test_empty_scan_returns_error(self):
        response = self.client.post(self.scan_url(), {"ticket_code": ""}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["status"], "error")

    def test_integrity_error_path_returns_duplicate_not_500(self):
        original_create = CheckInRecord.objects.create

        class RacingQuerySet:
            def get_or_create(self, *args, **kwargs):
                original_create(check_in=self_check_in.other_check_in, registration=self_check_in.registration)
                raise IntegrityError("simulated duplicate insert")

        self_check_in = self
        with patch("event.views.checkin.CheckInRecord.objects.select_related", return_value=RacingQuerySet()):
            response = self.client.post(self.scan_url(), {"ticket_code": self.registration.ticket_code}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "duplicate")
        self.assertEqual(response.data["existing_check_in"]["id"], str(self.other_check_in.pk))

    def test_status_returns_event_and_station_counts(self):
        second_member = make_member(email="remaining@example.com", first_name="Grace", last_name="Hopper")
        make_registration(second_member, self.event, self.ticket)
        CheckInRecord.objects.create(check_in=self.other_check_in, registration=self.registration)

        response = self.client.get(self.status_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["scanned"], 1)
        self.assertEqual(response.data["station_scanned"], 0)
        self.assertEqual(response.data["check_in"]["id"], str(self.check_in.pk))
        self.assertEqual(len(response.data["not_checked_in"]), 1)
        self.assertEqual(response.data["not_checked_in"][0]["email"], "remaining@example.com")
        self.assertEqual(response.data["recent_scans"], [])

    def test_status_includes_recent_station_scans(self):
        record = CheckInRecord.objects.create(check_in=self.check_in, registration=self.registration)

        response = self.client.get(self.status_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["station_scanned"], 1)
        self.assertEqual(response.data["recent_scans"][0]["id"], str(record.pk))
        self.assertEqual(response.data["recent_scans"][0]["attendee"]["ticket_code"], self.registration.ticket_code)

    def test_undo_removes_current_station_record(self):
        record = CheckInRecord.objects.create(check_in=self.check_in, registration=self.registration)

        response = self.client.post(self.undo_url(record), {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "removed")
        self.assertEqual(response.data["scanned"], 0)
        self.assertEqual(response.data["station_scanned"], 0)
        self.assertFalse(CheckInRecord.objects.filter(pk=record.pk).exists())

    def test_undo_cannot_remove_other_station_record(self):
        record = CheckInRecord.objects.create(check_in=self.other_check_in, registration=self.registration)

        response = self.client.post(self.undo_url(record), {}, format="json")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(CheckInRecord.objects.filter(pk=record.pk).exists())

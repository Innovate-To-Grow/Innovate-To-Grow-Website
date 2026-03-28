"""Tests for HealthCheckMiddleware responses and maintenance status."""

import json

from django.test import TestCase

from core.models import SiteMaintenanceControl


class HealthCheckMiddlewareTest(TestCase):
    URL = "/health/"

    def test_returns_200_and_ok_status(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["database"], "ok")
        self.assertFalse(data["maintenance"])

    def test_returns_json_content_type(self):
        response = self.client.get(self.URL)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_maintenance_mode_returns_200_with_maintenance_status(self):
        SiteMaintenanceControl.objects.create(
            pk=1,
            is_maintenance=True,
            message="Scheduled downtime",
        )
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "maintenance")
        self.assertTrue(data["maintenance"])
        self.assertEqual(data["maintenance_message"], "Scheduled downtime")

    def test_maintenance_off_returns_ok_status(self):
        SiteMaintenanceControl.objects.create(pk=1, is_maintenance=False)
        response = self.client.get(self.URL)

        data = json.loads(response.content)
        self.assertEqual(data["status"], "ok")
        self.assertFalse(data["maintenance"])

    def test_non_health_path_passes_through(self):
        response = self.client.get("/")
        self.assertNotEqual(response["Content-Type"], "application/json")

"""Tests for the MaintenanceBypassView."""

from functools import partial

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.authn.models import Member
from apps.authn.tests.stale_bearer import (
    assert_stale_bearer_reads_as_anonymous,
    stale_bearer_headers,
    valid_bearer_header,
)
from apps.core.models import SiteMaintenanceControl


class MaintenanceBypassViewTest(TestCase):
    URL = "/maintenance/bypass/"

    def test_missing_password_returns_400(self):
        response = self.client.post(self.URL, data={}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_not_in_maintenance_returns_400(self):
        SiteMaintenanceControl.objects.create(pk=1, is_maintenance=False)
        response = self.client.post(self.URL, data={"password": "abc"}, content_type="application/json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("not active", response.json()["error"])

    def test_bypass_not_configured_returns_400(self):
        SiteMaintenanceControl.objects.create(pk=1, is_maintenance=True, bypass_password="")
        response = self.client.post(self.URL, data={"password": "abc"}, content_type="application/json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("not configured", response.json()["error"])

    def test_wrong_password_returns_403(self):
        SiteMaintenanceControl.objects.create(pk=1, is_maintenance=True, bypass_password="correct")
        response = self.client.post(self.URL, data={"password": "wrong"}, content_type="application/json")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_correct_password_returns_200(self):
        SiteMaintenanceControl.objects.create(pk=1, is_maintenance=True, bypass_password="secret123")
        response = self.client.post(self.URL, data={"password": "secret123"}, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_legacy_plaintext_password_still_works(self):
        SiteMaintenanceControl.objects.create(pk=1, is_maintenance=True, bypass_password="secret123")
        SiteMaintenanceControl.objects.filter(pk=1).update(bypass_password="legacy-secret")

        response = self.client.post(self.URL, data={"password": "legacy-secret"}, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])


class MaintenanceBypassRequestTests(TestCase):
    """The password in the body is the only credential: the Authorization header and a malformed body are not."""

    URL = "/maintenance/bypass/"

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        SiteMaintenanceControl.objects.create(pk=1, is_maintenance=True, bypass_password="secret123")

    def post_raw(self, body, **extra):
        return self.client.post(self.URL, data=body, content_type="application/json", **extra)

    def test_stale_bearer_reads_as_anonymous(self):
        for body in ('{"password": "wrong"}', '{"password": ""}'):
            with self.subTest(body=body):
                assert_stale_bearer_reads_as_anonymous(self, partial(self.post_raw, body))

    def test_correct_password_with_a_stale_bearer_still_bypasses(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label):
                response = self.post_raw('{"password": "secret123"}', HTTP_AUTHORIZATION=header)

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.data["success"])

    def test_the_bearer_does_not_bypass_maintenance_by_itself(self):
        member = Member.objects.create_user(password="testpass123", is_staff=True, is_superuser=True)

        response = self.post_raw('{"password": "wrong"}', HTTP_AUTHORIZATION=valid_bearer_header(member))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])

    def test_body_that_is_not_an_object_is_a_400_not_a_500(self):
        for label, body in {
            "null": "null",
            "list": '["secret123"]',
            "string": '"secret123"',
            "number": "123",
            "boolean": "true",
        }.items():
            with self.subTest(body=label):
                response = self.post_raw(body)

                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.data["success"])
                self.assertEqual(response.data["error"], "Password is required.")

    def test_password_that_is_not_a_string_is_a_400_not_a_500(self):
        for label, body in {
            "null": '{"password": null}',
            "number": '{"password": 123}',
            "boolean": '{"password": true}',
            "list": '{"password": ["secret123"]}',
            "object": '{"password": {"a": 1}}',
        }.items():
            with self.subTest(password=label):
                response = self.post_raw(body)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["error"], "Password is required.")

    def test_password_that_can_never_be_stored_reads_as_missing(self):
        # A lone surrogate cannot be UTF-8 encoded (it used to be a 500) and a NUL is rejected by Django's form
        # fields, so neither can be the bypass password.
        for label, body in {"lone surrogate": '{"password": "\\ud800"}', "NUL": '{"password": "abc\\u0000"}'}.items():
            with self.subTest(password=label):
                response = self.post_raw(body)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["error"], "Password is required.")

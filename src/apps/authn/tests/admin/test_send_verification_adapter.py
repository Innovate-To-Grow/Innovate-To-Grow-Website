from django.core.cache import cache
from django.http import HttpResponse
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, Member, SendVerificationChallenge
from apps.authn.views.admin.login_helpers import LAST_ADMIN_LOGIN_COOKIE_NAME, set_last_admin_login_cookie


@override_settings(SEND_VERIFICATION_TEST_AUTOSOLVE=False, SEND_VERIFICATION_MODE="enforce")
class AdminSendVerificationAdapterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.member = Member.objects.create_user(password="Passphrase123!", is_staff=True, is_active=True)
        ContactEmail.objects.create(
            member=self.member, email_address="staff@example.com", email_type="primary", verified=True
        )
        response = HttpResponse()
        set_last_admin_login_cookie(response, self.member)
        self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = response.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME]
        self.client.get(reverse("admin-login"))
        self.csrf = self.client.cookies["csrftoken"].value
        self.url = reverse("admin-send-verification-challenge")

    def test_remembered_challenge_uses_admin_cookie_and_session(self):
        response = self.client.post(
            self.url,
            {"operation": "admin.login.remembered_code"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(response.status_code, 200)
        row = SendVerificationChallenge.objects.get(pk=response.json()["challenge_id"])
        self.assertEqual(row.destination_normalized, "staff@example.com")
        self.assertEqual(row.principal_type, "session")
        self.assertEqual(self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME]["path"], "/admin/")

    def test_challenge_requires_csrf(self):
        response = self.client.post(
            self.url, {"operation": "admin.login.remembered_code"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(SendVerificationChallenge.objects.exists())

    def test_admin_adapter_rejects_public_operations(self):
        response = self.client.post(
            self.url,
            {"operation": "login.request_code", "email": "staff@example.com"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SendVerificationChallenge.objects.exists())

    def test_public_adapter_rejects_admin_operations(self):
        response = self.client.post(
            "/authn/send-verification/challenge/",
            {"operation": "admin.login.remembered_code"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(STATIC_URL="https://assets.school.example/static/")
    def test_login_resolves_widget_asset_through_static_storage(self):
        response = self.client.get(reverse("admin-login"))
        self.assertContains(
            response, 'data-altcha-url="https://assets.school.example/static/vendor/altcha/altcha.umd.js"'
        )
        self.assertContains(response, 'data-challenge-url="/admin/send-verification/challenge/"')

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import TestCase
from django.test.client import RequestFactory

from apps.event.tests.helpers import make_superuser


class SMTPProviderConfigAdminTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        from apps.core.admin.service_credentials.aws_smtp.smtp import SMTPProviderConfigAdmin
        from apps.core.models import SMTPProviderConfig

        self.model = SMTPProviderConfig
        self.admin = SMTPProviderConfigAdmin(SMTPProviderConfig, AdminSite())

    def _request(self):
        request = RequestFactory().get("/")
        request.user = self.admin_user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_status_badge_active_and_inactive(self):
        self.assertEqual(self.admin.status_badge(self.model(is_active=True)), ("Active", "success"))
        self.assertEqual(self.admin.status_badge(self.model(is_active=False)), ("Inactive", "danger"))

    def test_security_ssl_tls_and_none(self):
        self.assertEqual(self.admin.security(self.model(use_ssl=True, use_tls=False)), "SSL")
        self.assertEqual(self.admin.security(self.model(use_ssl=False, use_tls=True)), "TLS")
        self.assertEqual(self.admin.security(self.model(use_ssl=False, use_tls=False)), "None")

    def test_has_delete_permission_blocked_for_active(self):
        active = self.model.objects.create(name="Active SMTP", host="smtp.example.com", is_active=True)
        inactive = self.model.objects.create(name="Inactive SMTP", host="smtp.example.com", is_active=False)
        self.assertFalse(self.admin.has_delete_permission(self._request(), active))
        self.assertTrue(self.admin.has_delete_permission(self._request(), inactive))
        self.assertTrue(self.admin.has_delete_permission(self._request(), None))

    def test_get_actions_removes_delete_selected(self):
        actions = self.admin.get_actions(self._request())
        self.assertNotIn("delete_selected", actions)

    def test_form_clean_password_keeps_existing_on_blank(self):
        from apps.core.admin.service_credentials.aws_smtp.smtp import SMTPProviderConfigForm

        config = self.model.objects.create(
            name="SMTP", host="smtp.example.com", username="user", password="stored-secret"
        )
        form = SMTPProviderConfigForm(
            data={
                "name": "SMTP",
                "host": "smtp.example.com",
                "port": 587,
                "use_tls": True,
                "timeout": 30,
                "username": "user",
                "password": "",
            },
            instance=config,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["password"], "stored-secret")

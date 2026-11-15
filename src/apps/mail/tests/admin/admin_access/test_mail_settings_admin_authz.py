from unittest.mock import patch

from django.urls import reverse

from apps.mail.tests.admin.admin_access.test_admin_authz import MailAdminAuthzTestBase


class MailSettingsAdminAuthzTest(MailAdminAuthzTestBase):
    def test_settings_view_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_settings")
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_settings_edit_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_settings_edit")
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_settings_edit_post_denied_for_grantless(self):
        url = reverse("admin:mail_settings_edit")
        self.assert_denied_for_grantless(url, method="post", data={})

    @patch("apps.mail.admin.settings.test_send._send_test_email")
    def test_test_email_get_denied_for_grantless_allowed_for_superuser(self, mock_send):
        url = reverse("admin:mail_settings_test_email")
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    @patch("apps.mail.admin.settings.test_send._send_test_email")
    def test_test_email_post_denied_for_grantless(self, mock_send):
        url = reverse("admin:mail_settings_test_email")
        self.assert_denied_for_grantless(url, method="post", data={"recipient": "x@example.com"})
        mock_send.assert_not_called()

    @patch("apps.mail.admin.settings.test_send._send_test_sms")
    def test_test_sms_get_denied_for_grantless_allowed_for_superuser(self, mock_send):
        url = reverse("admin:mail_settings_test_sms")
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    @patch("apps.mail.admin.settings.test_send._send_test_sms")
    def test_test_sms_post_denied_for_grantless(self, mock_send):
        url = reverse("admin:mail_settings_test_sms")
        self.assert_denied_for_grantless(url, method="post", data={"recipient": "2345678901", "country_code": "+1"})
        mock_send.assert_not_called()

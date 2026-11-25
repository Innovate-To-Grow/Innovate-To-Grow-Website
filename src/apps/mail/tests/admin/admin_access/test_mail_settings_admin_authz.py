from unittest.mock import patch

from django.urls import reverse

from apps.mail.tests.admin.admin_access.test_admin_authz import MailAdminAuthzTestBase


class MailSettingsAdminAuthzTest(MailAdminAuthzTestBase):
    def test_settings_view_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_settings")
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    def test_settings_edit_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_settings_edit")
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    def test_settings_edit_post_refused_to_members(self):
        url = reverse("admin:mail_settings_edit")
        self.assert_refused_to_member(url, method="post", data={})

    @patch("apps.mail.admin.settings.admin.test_send._send_test_email")
    def test_test_email_get_refused_to_members_allowed_for_admins(self, mock_send):
        url = reverse("admin:mail_settings_test_email")
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    @patch("apps.mail.admin.settings.admin.test_send._send_test_email")
    def test_test_email_post_refused_to_members(self, mock_send):
        url = reverse("admin:mail_settings_test_email")
        self.assert_refused_to_member(url, method="post", data={"recipient": "x@example.com"})
        mock_send.assert_not_called()

    @patch("apps.mail.admin.settings.admin.test_send._send_test_sms")
    def test_test_sms_get_refused_to_members_allowed_for_admins(self, mock_send):
        url = reverse("admin:mail_settings_test_sms")
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    @patch("apps.mail.admin.settings.admin.test_send._send_test_sms")
    def test_test_sms_post_refused_to_members(self, mock_send):
        url = reverse("admin:mail_settings_test_sms")
        self.assert_refused_to_member(url, method="post", data={"recipient": "2345678901", "country_code": "+1"})
        mock_send.assert_not_called()

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.cms.models import CMSEmbedAllowedHost
from apps.core.tests.admin.confirm.test_confirm_on_save import _confirm_change_data, _make_staff, _make_superuser


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmOnSaveChangeTest(TestCase):
    """Test confirmation flow for changing objects via admin."""

    def setUp(self):
        self.admin_user = _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.host = CMSEmbedAllowedHost.objects.create(hostname="original.com", is_active=True)

    def test_change_post_redirects_to_confirmation(self):
        url = reverse("admin:cms_cmsembedallowedhost_change", args=[self.host.pk])
        response = self.client.post(url, {"hostname": "changed.com", "is_active": True})

        self.assertEqual(response.status_code, 302)
        self.assertIn("confirm-change", response.url)

    def test_confirmation_page_shows_diff(self):
        url = reverse("admin:cms_cmsembedallowedhost_change", args=[self.host.pk])
        self.client.post(url, {"hostname": "changed.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        response = self.client.get(confirm_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Changing")
        self.assertContains(response, "original.com")
        self.assertContains(response, "changed.com")

    def test_confirmed_change_updates_object(self):
        url = reverse("admin:cms_cmsembedallowedhost_change", args=[self.host.pk])
        self.client.post(url, {"hostname": "updated.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, _confirm_change_data(self.client, "cms embed allowed host"))

        self.host.refresh_from_db()
        self.assertEqual(self.host.hostname, "updated.com")

    def test_no_change_skips_confirmation(self):
        url = reverse("admin:cms_cmsembedallowedhost_change", args=[self.host.pk])
        response = self.client.post(url, {"hostname": "original.com", "is_active": True})

        self.assertNotIn("confirm-change", response.url if response.status_code == 302 else "")

    @patch("apps.authn.services.email.send_email.senders.send_notification_email")
    def test_confirmed_change_does_not_notify_staff(self, mock_send):
        _make_staff(email="notify-change@example.com")

        url = reverse("admin:cms_cmsembedallowedhost_change", args=[self.host.pk])
        self.client.post(url, {"hostname": "notify-changed.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, _confirm_change_data(self.client, "cms embed allowed host"))

        self.host.refresh_from_db()
        self.assertEqual(self.host.hostname, "notify-changed.com")
        mock_send.assert_not_called()


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmOnSaveDeleteTest(TestCase):
    """Test confirmation flow for deleting objects via admin."""

    def setUp(self):
        self.admin_user = _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.host = CMSEmbedAllowedHost.objects.create(hostname="to-delete.com", is_active=True)

    def test_delete_post_redirects_to_confirmation(self):
        url = reverse("admin:cms_cmsembedallowedhost_delete", args=[self.host.pk])
        response = self.client.post(url, {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.assertIn("confirm-change", response.url)

    def test_confirmation_page_shows_delete_details(self):
        url = reverse("admin:cms_cmsembedallowedhost_delete", args=[self.host.pk])
        self.client.post(url, {"post": "yes"})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        response = self.client.get(confirm_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deleting")
        self.assertContains(response, "to-delete.com")

    def test_confirmed_delete_removes_object(self):
        url = reverse("admin:cms_cmsembedallowedhost_delete", args=[self.host.pk])
        self.client.post(url, {"post": "yes"})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, _confirm_change_data(self.client, "cms embed allowed host"))

        self.assertFalse(CMSEmbedAllowedHost.objects.filter(pk=self.host.pk).exists())

    def test_wrong_word_does_not_delete(self):
        url = reverse("admin:cms_cmsembedallowedhost_delete", args=[self.host.pk])
        self.client.post(url, {"post": "yes"})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, _confirm_change_data(self.client, "NOPE"), follow=True)

        self.assertTrue(CMSEmbedAllowedHost.objects.filter(pk=self.host.pk).exists())

    @patch("apps.authn.services.email.send_email.senders.send_notification_email")
    def test_confirmed_delete_does_not_notify_staff(self, mock_send):
        _make_staff(email="notify-del@example.com")

        url = reverse("admin:cms_cmsembedallowedhost_delete", args=[self.host.pk])
        self.client.post(url, {"post": "yes"})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, _confirm_change_data(self.client, "cms embed allowed host"))

        self.assertFalse(CMSEmbedAllowedHost.objects.filter(pk=self.host.pk).exists())
        mock_send.assert_not_called()


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmOnSaveSkipTest(TestCase):
    """Test that confirmation is skipped in appropriate cases."""

    def setUp(self):
        self.admin_user = _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_popup_mode_skips_confirmation(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        response = self.client.post(url, {"hostname": "popup.com", "is_active": True, "_popup": "1"})

        self.assertNotIn("confirm-change", response.url if response.status_code == 302 else "")
        self.assertTrue(CMSEmbedAllowedHost.objects.filter(hostname="popup.com").exists())

    def test_no_pending_change_shows_error(self):
        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        response = self.client.get(confirm_url, follow=True)

        self.assertContains(response, "No pending change found")

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_disabled_setting_saves_directly(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        response = self.client.post(url, {"hostname": "direct-save.com", "is_active": True})

        self.assertTrue(CMSEmbedAllowedHost.objects.filter(hostname="direct-save.com").exists())


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmOnSaveValidationTest(TestCase):
    """Test that form validation errors are shown normally without confirmation."""

    def setUp(self):
        self.admin_user = _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_invalid_form_shows_errors_not_confirmation(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        response = self.client.post(url, {"hostname": "", "is_active": True})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("confirm-change", response.get("Location", ""))

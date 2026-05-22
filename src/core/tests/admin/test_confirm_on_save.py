"""Tests for the ConfirmOnSaveMixin and admin notifications."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from authn.models import ContactEmail
from cms.models import CMSEmbedAllowedHost

User = get_user_model()


def _make_superuser(email="admin@example.com"):
    user = User.objects.create_superuser(password="testpass123", first_name="Admin", last_name="User")
    ContactEmail.objects.create(member=user, email_address=email, email_type="primary", verified=True)
    return user


def _make_staff(email="staff@example.com"):
    user = User.objects.create_user(password="testpass123", is_staff=True, first_name="Staff", last_name="Member")
    ContactEmail.objects.create(member=user, email_address=email, email_type="primary", verified=True)
    return user


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmOnSaveAddTest(TestCase):
    """Test confirmation flow for adding objects via admin."""

    def setUp(self):
        self.admin_user = _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_add_post_redirects_to_confirmation_page(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        response = self.client.post(url, {"hostname": "example.com", "is_active": True})

        self.assertEqual(response.status_code, 302)
        self.assertIn("confirm-change", response.url)

    def test_confirmation_page_shows_new_values(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "new-host.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        response = self.client.get(confirm_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Adding")
        self.assertContains(response, "new-host.com")

    def test_confirmation_page_requires_typed_word(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "typed-test.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        response = self.client.get(confirm_url)

        self.assertContains(response, 'Type <strong>"')
        self.assertContains(response, "confirm-input")

    def test_wrong_confirmation_word_shows_error(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "wrong-word.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        response = self.client.post(confirm_url, {"confirmation_word": "WRONG"}, follow=True)

        self.assertContains(response, "Please type")
        self.assertFalse(CMSEmbedAllowedHost.objects.filter(hostname="wrong-word.com").exists())

    def test_correct_confirmation_word_saves_object(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "confirmed.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        confirmation_word = "cms embed allowed host"
        response = self.client.post(confirm_url, {"confirmation_word": confirmation_word})

        self.assertTrue(CMSEmbedAllowedHost.objects.filter(hostname="confirmed.com").exists())

    def test_case_insensitive_confirmation(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "case-test.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        response = self.client.post(confirm_url, {"confirmation_word": "CMS Embed Allowed Host"})

        self.assertTrue(CMSEmbedAllowedHost.objects.filter(hostname="case-test.com").exists())

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_notification_email_sent_after_add(self, mock_send):
        _make_staff(email="other-staff@example.com")

        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "notify-add.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, {"confirmation_word": "cms embed allowed host"})

        mock_send.assert_called()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "other-staff@example.com")
        self.assertIn("Added", call_kwargs["subject"])

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_notification_excludes_actor(self, mock_send):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "exclude-actor.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, {"confirmation_word": "cms embed allowed host"})

        for call in mock_send.call_args_list:
            self.assertNotEqual(call[1]["recipient"], "admin@example.com")


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
        self.client.post(confirm_url, {"confirmation_word": "cms embed allowed host"})

        self.host.refresh_from_db()
        self.assertEqual(self.host.hostname, "updated.com")

    def test_no_change_skips_confirmation(self):
        url = reverse("admin:cms_cmsembedallowedhost_change", args=[self.host.pk])
        response = self.client.post(url, {"hostname": "original.com", "is_active": True})

        self.assertNotIn("confirm-change", response.url if response.status_code == 302 else "")

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_notification_email_sent_after_change(self, mock_send):
        _make_staff(email="notify-change@example.com")

        url = reverse("admin:cms_cmsembedallowedhost_change", args=[self.host.pk])
        self.client.post(url, {"hostname": "notify-changed.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, {"confirmation_word": "cms embed allowed host"})

        mock_send.assert_called()
        call_kwargs = mock_send.call_args[1]
        self.assertIn("Changed", call_kwargs["subject"])


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
        self.client.post(confirm_url, {"confirmation_word": "cms embed allowed host"})

        self.assertFalse(CMSEmbedAllowedHost.objects.filter(pk=self.host.pk).exists())

    def test_wrong_word_does_not_delete(self):
        url = reverse("admin:cms_cmsembedallowedhost_delete", args=[self.host.pk])
        self.client.post(url, {"post": "yes"})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, {"confirmation_word": "NOPE"}, follow=True)

        self.assertTrue(CMSEmbedAllowedHost.objects.filter(pk=self.host.pk).exists())

    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_notification_email_sent_after_delete(self, mock_send):
        _make_staff(email="notify-del@example.com")

        url = reverse("admin:cms_cmsembedallowedhost_delete", args=[self.host.pk])
        self.client.post(url, {"post": "yes"})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, {"confirmation_word": "cms embed allowed host"})

        mock_send.assert_called()
        call_kwargs = mock_send.call_args[1]
        self.assertIn("Deleted", call_kwargs["subject"])


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

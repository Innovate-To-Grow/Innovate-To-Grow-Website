"""Tests for the ConfirmOnSaveMixin."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.cms.models import CMSEmbedAllowedHost

User = get_user_model()
CHANGE_SESSION_KEY = "_admin_pending_change_cms_cmsembedallowedhost"


def _make_superuser(email="admin@example.com"):
    user = User.objects.create_superuser(password="testpass123", first_name="Admin", last_name="User")
    ContactEmail.objects.create(member=user, email_address=email, email_type="primary", verified=True)
    return user


def _make_staff(email="staff@example.com"):
    user = User.objects.create_user(password="testpass123", is_staff=True, first_name="Staff", last_name="Member")
    ContactEmail.objects.create(member=user, email_address=email, email_type="primary", verified=True)
    return user


def _confirm_change_data(client, confirmation_word, *, token=None):
    return {
        "confirmation_word": confirmation_word,
        "token": token or client.session[CHANGE_SESSION_KEY]["token"],
    }


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmViewAccessTest(TestCase):
    """The confirm-change/confirm-action custom admin URLs are wrapped in admin_view: a member who is not an Admin is
    sent to the admin sign-in, any Admin reaches them."""

    def _login(self, *, is_staff):
        member = User.objects.create_user(password="testpass123", is_staff=is_staff)
        ContactEmail.objects.create(member=member, email_address="outsider@example.com", email_type="primary")
        self.client.force_login(member)

    def test_a_member_who_is_not_an_admin_is_sent_to_the_sign_in(self):
        self._login(is_staff=False)
        for name in ("confirm_change", "confirm_action"):
            with self.subTest(name):
                response = self.client.get(reverse(f"admin:cms_cmsembedallowedhost_{name}"))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login/", response["Location"])

    def test_an_admin_is_not_forbidden(self):
        self._login(is_staff=True)
        for name in ("confirm_change", "confirm_action"):
            with self.subTest(name):
                # No pending change in session -> redirects to the changelist, not a 403.
                response = self.client.get(reverse(f"admin:cms_cmsembedallowedhost_{name}"))
                self.assertNotEqual(response.status_code, 403)
                self.assertNotIn("/admin/login/", response.get("Location", ""))


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

    def test_pending_change_uses_model_specific_session_key(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "session-key.com", "is_active": True})

        session = self.client.session
        self.assertIn(CHANGE_SESSION_KEY, session)
        self.assertNotIn("_admin_pending_change", session)

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
        response = self.client.post(confirm_url, _confirm_change_data(self.client, "WRONG"), follow=True)

        self.assertContains(response, "Please type")
        self.assertFalse(CMSEmbedAllowedHost.objects.filter(hostname="wrong-word.com").exists())

    def test_invalid_token_rejects_the_save_but_keeps_the_pending_change(self):
        """A stale tab's wrong token must not destroy the pending change it did not match.

        There is one pending slot per model, so a second submission (from another tab) replaces
        it — discarding on mismatch threw away the edits the admin was about to confirm, in
        addition to refusing this one.
        """
        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "bad-token.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        response = self.client.post(
            confirm_url,
            _confirm_change_data(self.client, "cms embed allowed host", token="not-the-session-token"),
            follow=True,
        )

        self.assertContains(response, "Invalid confirmation token")
        self.assertFalse(CMSEmbedAllowedHost.objects.filter(hostname="bad-token.com").exists())
        self.assertIn(CHANGE_SESSION_KEY, self.client.session)

        # ...and the real token still works, so nothing was lost.
        self.client.post(confirm_url, _confirm_change_data(self.client, "cms embed allowed host"))
        self.assertTrue(CMSEmbedAllowedHost.objects.filter(hostname="bad-token.com").exists())

    def test_correct_confirmation_word_saves_object(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "confirmed.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        confirmation_word = "cms embed allowed host"
        self.client.post(confirm_url, _confirm_change_data(self.client, confirmation_word))

        self.assertTrue(CMSEmbedAllowedHost.objects.filter(hostname="confirmed.com").exists())

    def test_case_insensitive_confirmation(self):
        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "case-test.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, _confirm_change_data(self.client, "CMS Embed Allowed Host"))

        self.assertTrue(CMSEmbedAllowedHost.objects.filter(hostname="case-test.com").exists())

    @patch("apps.authn.services.email.send_email.senders.send_notification_email")
    def test_confirmed_add_does_not_notify_staff(self, mock_send):
        _make_staff(email="other-staff@example.com")

        url = reverse("admin:cms_cmsembedallowedhost_add")
        self.client.post(url, {"hostname": "notify-add.com", "is_active": True})

        confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")
        self.client.post(confirm_url, _confirm_change_data(self.client, "cms embed allowed host"))

        self.assertTrue(CMSEmbedAllowedHost.objects.filter(hostname="notify-add.com").exists())
        mock_send.assert_not_called()

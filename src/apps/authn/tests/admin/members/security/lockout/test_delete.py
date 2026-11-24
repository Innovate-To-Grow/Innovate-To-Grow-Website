"""Deleting a member keeps the lockout rules: never your own Admin account, never the last active Admin."""

from django.contrib import admin
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, Member
from apps.authn.tests.admin.members.security.admins.fixtures import AdminPeersCase

OWN_ACCOUNT = "You cannot delete your own Admin account."
LAST_ADMIN = "the site must keep at least one active Admin"
CONFIRMATION_WORD = str(Member._meta.verbose_name)


def texts(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


class _DeleteCase(AdminPeersCase):
    def delete_url(self, member):
        return reverse("admin:authn_member_delete", args=[member.pk])

    def direct_request(self, user):
        request = RequestFactory().post("/")
        request.user = user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class DeletePageTests(_DeleteCase):
    def test_your_own_delete_page_sends_you_back_with_the_reason(self):
        for response in (self.client.get(self.delete_url(self.admin)), self.client.post(self.delete_url(self.admin))):
            self.assertRedirects(
                response, reverse("admin:authn_member_change", args=[self.admin.pk]), fetch_redirect_response=False
            )
            self.assertTrue(any(OWN_ACCOUNT in text for text in texts(response)))
        self.assertTrue(Member.objects.filter(pk=self.admin.pk).exists())

    def test_the_delete_page_still_opens_for_another_member(self):
        self.assertEqual(self.client.get(self.delete_url(self.regular)).status_code, 200)

    def test_an_unknown_member_is_left_to_django(self):
        response = self.client.get(reverse("admin:authn_member_delete", args=["00000000-0000-0000-0000-000000000000"]))

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/change/", response["Location"])

    def test_delete_model_refuses_the_last_active_admin(self):
        Member.objects.filter(pk=self.other_admin.pk).update(is_active=False)
        model_admin = admin.site._registry[Member]

        with self.assertRaisesMessage(PermissionDenied, LAST_ADMIN):
            model_admin.delete_model(self.direct_request(self.regular), self.admin)

        self.assertTrue(Member.objects.filter(pk=self.admin.pk).exists())

    def test_delete_model_deletes_another_member(self):
        model_admin = admin.site._registry[Member]

        model_admin.delete_model(self.direct_request(self.admin), self.regular)

        self.assertFalse(Member.objects.filter(pk=self.regular.pk).exists())


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class DeletePageWithConfirmationTests(_DeleteCase):
    def test_your_own_delete_is_refused_before_the_confirmation_page(self):
        response = self.client.post(self.delete_url(self.admin), {"post": "yes"})

        self.assertRedirects(
            response, reverse("admin:authn_member_change", args=[self.admin.pk]), fetch_redirect_response=False
        )
        self.assertTrue(Member.objects.filter(pk=self.admin.pk).exists())

    def test_another_admin_is_deleted_after_the_typed_confirmation(self):
        ContactEmail.objects.filter(member=self.other_admin).delete()
        held = self.client.post(self.delete_url(self.other_admin), {"post": "yes"})
        confirm_url = reverse("admin:authn_member_confirm_change")
        self.assertRedirects(held, confirm_url, fetch_redirect_response=False)
        token = self.client.session["_admin_pending_change_authn_member"]["token"]

        self.client.post(confirm_url, {"token": token, "confirmation_word": CONFIRMATION_WORD})

        self.assertFalse(Member.objects.filter(pk=self.other_admin.pk).exists())

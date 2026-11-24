"""The bulk Deactivate and Delete actions check the whole selection against the lockout rules, select-all included."""

from django.contrib import admin
from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.urls import reverse

from apps.authn.admin.members.member.helpers import deactivate_members
from apps.authn.models import ContactEmail, Member
from apps.authn.tests.admin.members.security.lockout.test_delete import CONFIRMATION_WORD, LAST_ADMIN, _DeleteCase


def texts(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class BulkLockoutTests(_DeleteCase):
    def select_all(self, action, **extra):
        # ``select_across`` acts on every member the list shows, whatever single row is ticked.
        return self.changelist_action(action, [self.regular], select_across="1", **extra)

    def test_deactivating_everyone_is_refused_as_a_whole(self):
        response = self.select_all("deactivate_members")

        self.assertTrue(any("You cannot deactivate your own Admin account" in text for text in texts(response)))
        self.assertEqual(Member.objects.filter(is_active=False).count(), 0)

    def test_deactivating_yourself_is_refused(self):
        self.changelist_action("deactivate_members", [self.admin, self.regular])

        self.assertTrue(Member.objects.get(pk=self.admin.pk).is_active)
        self.assertTrue(Member.objects.get(pk=self.regular.pk).is_active)

    def test_deactivating_another_admin_also_removes_their_admin_access(self):
        self.changelist_action("deactivate_members", [self.other_admin])

        stored = Member.objects.values("is_active", "is_staff", "is_superuser").get(pk=self.other_admin.pk)
        self.assertEqual(stored, {"is_active": False, "is_staff": False, "is_superuser": False})

    def test_the_last_active_admin_is_not_deactivated(self):
        Member.objects.filter(pk=self.other_admin.pk).update(is_active=False)
        request = self.direct_request(self.regular)

        deactivate_members(admin.site._registry[Member], request, Member.objects.filter(pk=self.admin.pk))

        self.assertTrue(Member.objects.get(pk=self.admin.pk).is_active)
        self.assertTrue(any(LAST_ADMIN in str(message) for message in request._messages))

    def test_deleting_everyone_is_refused_before_the_confirmation_page(self):
        for extra in ({}, {"post": "yes"}):
            with self.subTest(confirmed=bool(extra)):
                response = self.select_all("delete_selected", **extra)

                self.assertEqual(response.status_code, 302)
                self.assertTrue(any("You cannot delete your own Admin account" in text for text in texts(response)))
        self.assertEqual(Member.objects.count(), 3)

    def test_delete_queryset_refuses_your_own_account(self):
        request = self.direct_request(self.admin)

        with self.assertRaisesMessage(PermissionDenied, "your own Admin account"):
            admin.site._registry[Member].delete_queryset(request, Member.objects.all())

        self.assertEqual(Member.objects.count(), 3)

    def test_delete_queryset_refuses_the_last_active_admin(self):
        Member.objects.filter(pk=self.other_admin.pk).update(is_staff=False)

        with self.assertRaisesMessage(PermissionDenied, LAST_ADMIN):
            admin.site._registry[Member].delete_queryset(
                self.direct_request(self.regular), Member.objects.filter(pk=self.admin.pk)
            )

    def test_a_selection_without_you_is_deleted(self):
        ContactEmail.objects.filter(member=self.other_admin).delete()

        self.changelist_action("delete_selected", [self.other_admin, self.regular], post="yes")

        self.assertEqual(list(Member.objects.values_list("pk", flat=True)), [self.admin.pk])


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class BulkLockoutWithConfirmationTests(_DeleteCase):
    def confirm(self, action, members):
        held = self.changelist_action(action, members)
        confirm_url = reverse("admin:authn_member_confirm_action")
        self.assertRedirects(held, confirm_url, fetch_redirect_response=False)
        token = self.client.session["_admin_pending_action_authn_member"]["token"]
        return self.client.post(confirm_url, {"token": token, "confirmation_word": CONFIRMATION_WORD})

    def test_a_confirmed_deactivation_of_yourself_still_changes_nothing(self):
        response = self.confirm("deactivate_members", [self.admin, self.other_admin])

        self.assertTrue(any("You cannot deactivate your own Admin account" in text for text in texts(response)))
        self.assertEqual(Member.objects.filter(is_active=False).count(), 0)

    def test_a_confirmed_delete_of_yourself_still_deletes_nothing(self):
        response = self.confirm("delete_selected", [self.admin, self.regular])

        self.assertTrue(any("You cannot delete your own Admin account" in text for text in texts(response)))
        self.assertEqual(Member.objects.count(), 3)

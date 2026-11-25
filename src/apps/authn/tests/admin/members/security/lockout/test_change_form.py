"""The Member change form keeps the lockout rules: never your own Admin access, never the last active Admin."""

from django.contrib import admin
from django.forms import modelform_factory
from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.authn.admin.members.member.forms import MemberChangeForm
from apps.authn.admin.members.member.lockout import OWN_ACCOUNT_NOTE
from apps.authn.models import Member
from apps.authn.tests.admin.members.forms.change.test_member_admin_change_page import build_change_post_data
from apps.authn.tests.admin.members.security.admins.fixtures import AdminPeersCase

LAST_ADMIN = "the site must keep at least one active Admin"
OWN_ACCOUNT = "your own Admin account"


def _flags_form(actor, member, **data):
    form_class = modelform_factory(Member, form=MemberChangeForm, fields=("is_staff", "is_active"))
    form_class.removal_actor = actor
    return form_class(data={key: "on" for key, value in data.items() if value}, instance=member)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class OwnChangePageTests(AdminPeersCase):
    def test_admin_and_account_active_are_read_only_on_your_own_page(self):
        request = RequestFactory().get("/")
        request.user = self.admin
        readonly = admin.site._registry[Member].get_readonly_fields(request, self.admin)

        self.assertIn("is_staff", readonly)
        self.assertIn("is_active", readonly)

    def test_your_own_page_says_why(self):
        own = self.client.get(reverse("admin:authn_member_change", args=[self.admin.pk]))
        other = self.client.get(reverse("admin:authn_member_change", args=[self.other_admin.pk]))

        self.assertContains(own, OWN_ACCOUNT_NOTE)
        self.assertNotContains(own, 'name="is_staff"')
        self.assertNotContains(other, OWN_ACCOUNT_NOTE)
        self.assertContains(other, 'name="is_staff"')

    def test_a_forged_post_on_your_own_page_keeps_your_admin_access(self):
        url = reverse("admin:authn_member_change", args=[self.admin.pk])
        data = build_change_post_data(self.client, url)
        data.pop("is_staff", None)
        data.pop("is_active", None)

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_staff and self.admin.is_active)


class FlagsFormTests(AdminPeersCase):
    def test_another_admin_may_remove_admin_access(self):
        self.assertTrue(_flags_form(self.admin, self.other_admin, is_active=True).is_valid())

    def test_another_admin_may_deactivate_an_admin(self):
        self.assertTrue(_flags_form(self.admin, self.other_admin, is_staff=True).is_valid())

    def test_your_own_admin_access_is_refused(self):
        form = _flags_form(self.admin, self.admin, is_active=True)

        self.assertFalse(form.is_valid())
        self.assertIn(OWN_ACCOUNT, form.errors["is_staff"][0])

    def test_deactivating_your_own_admin_account_is_refused(self):
        form = _flags_form(self.admin, self.admin, is_staff=True)

        self.assertFalse(form.is_valid())
        self.assertIn(OWN_ACCOUNT, form.errors["is_active"][0])

    def test_the_last_active_admin_keeps_admin_access(self):
        self.other_admin.is_active = False
        self.other_admin.save(update_fields=["is_active"])

        demote = _flags_form(None, self.admin, is_active=True)
        deactivate = _flags_form(self.regular, self.admin, is_staff=True)

        self.assertFalse(demote.is_valid())
        self.assertIn(LAST_ADMIN, demote.errors["is_staff"][0])
        self.assertFalse(deactivate.is_valid())
        self.assertIn(LAST_ADMIN, deactivate.errors["is_active"][0])

    def test_regular_members_and_unchanged_flags_pass(self):
        self.assertTrue(_flags_form(self.admin, self.regular).is_valid())
        self.assertTrue(_flags_form(None, self.admin, is_staff=True, is_active=True).is_valid())

    def test_an_unsaved_member_has_nothing_to_remove(self):
        unsaved = Member(is_staff=True, is_active=True)

        self.assertTrue(_flags_form(unsaved, unsaved).is_valid())


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class ChangePageSaveTests(AdminPeersCase):
    def post_flags(self, member, **flags):
        url = reverse("admin:authn_member_change", args=[member.pk])
        data = build_change_post_data(self.client, url)
        for field, value in flags.items():
            if value:
                data[field] = "on"
            else:
                data.pop(field, None)
        return self.client.post(url, data)

    def test_an_admin_can_remove_another_admins_access(self):
        response = self.post_flags(self.other_admin, is_staff=False)

        self.assertEqual(response.status_code, 302)
        self.other_admin.refresh_from_db()
        self.assertEqual((self.other_admin.is_staff, self.other_admin.is_superuser), (False, False))

    def test_an_admin_can_make_a_regular_member_an_admin(self):
        response = self.post_flags(self.regular, is_staff=True)

        self.assertEqual(response.status_code, 302)
        self.regular.refresh_from_db()
        self.assertEqual((self.regular.is_staff, self.regular.is_superuser), (True, True))
